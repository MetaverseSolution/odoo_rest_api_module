# -*- coding: utf-8 -*-
import json
import math
import logging
import requests

from odoo import http, _, exceptions
from odoo.http import request

from .serializers import Serializer
from .exceptions import QueryFormatError


_logger = logging.getLogger(__name__)


def error_response(error, msg):
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": 200,
            "message": msg,
            "data": {
                "name": str(error),
                "debug": "",
                "message": msg,
                "arguments": list(error.args),
                "exception_type": type(error).__name__
            }
        }
    }


class OdooAPI(http.Controller):
    @http.route(
        '/auth/',
        type='json', auth='none', methods=["POST"], csrf=False)
    def authenticate(self, *args, **post):
        try:
            login = post["login"]
        except KeyError:
            raise exceptions.AccessDenied(message='`login` is required.')

        try:
            password = post["password"]
        except KeyError:
            raise exceptions.AccessDenied(message='`password` is required.')

        try:
            db = post["db"]
        except KeyError:
            raise exceptions.AccessDenied(message='`db` is required.')

        http.request.session.authenticate(db, login, password)
        res = request.env['ir.http'].session_info()
        return res

    @http.route(
        '/object/<string:model>/<string:function>',
        type='json', auth='user', methods=["POST"], csrf=False)
    def call_model_function(self, model, function, **post):
        args = []
        kwargs = {}
        if "args" in post:
            args = post["args"]
        if "kwargs" in post:
            kwargs = post["kwargs"]
        model = request.env[model]
        result = getattr(model, function)(*args, **kwargs)
        return result

    @http.route(
        '/object/<string:model>/<int:rec_id>/<string:function>',
        type='json', auth='user', methods=["POST"], csrf=False)
    def call_obj_function(self, model, rec_id, function, **post):
        args = []
        kwargs = {}
        if "args" in post:
            args = post["args"]
        if "kwargs" in post:
            kwargs = post["kwargs"]
        obj = request.env[model].browse(rec_id).ensure_one()
        result = getattr(obj, function)(*args, **kwargs)
        return result

    @http.route(
        '/api/<string:model>',
        type='http', auth='user', methods=['GET'], csrf=False)
    def get_model_data(self, model, **params):
        try:
            records = request.env[model].search([])
        except KeyError as e:
            msg = f"The model `{model}` does not exist."
            res = error_response(e, msg)
            return http.Response(
                json.dumps({
                    "status": 400,
                    "data": [],
                    "message": msg,
                    "total_pages": 0,
                    "page_number": 1,
                    "total_elements": 0
                }),
                status=200,
                mimetype='application/json'
            )

        if "query" in params:
            query = params["query"]
        else:
            query = "{*}"

        if "order" in params:
            orders = json.loads(params["order"])
        else:
            orders = ""

        if "filter" in params:
            filters = json.loads(params["filter"])
            records = request.env[model].search(filters, order=orders)

        total_page_number = 1
        current_page = 1

        if "page_size" in params:
            page_size = int(params["page_size"])
            count = len(records)
            total_page_number = math.ceil(count / page_size)

            if "page" in params:
                current_page = int(params["page"])
            else:
                current_page = 1
            start = page_size * (current_page - 1)
            stop = current_page * page_size
            records = records[start:stop]

        if "limit" in params:
            limit = int(params["limit"])
            records = records[0:limit]

        try:
            serializer = Serializer(records, query, many=True)
            data = serializer.data
        except (SyntaxError, QueryFormatError) as e:
            res = error_response(e, e.msg)
            return http.Response(
                json.dumps({
                    "status": 400,
                    "data": [],
                    "message": e.msg,
                    "total_pages": 0,
                    "page_number": current_page,
                    "total_elements": 0
                }),
                status=200,
                mimetype='application/json'
            )

        return http.Response(
            json.dumps({
                "status": 200,
                "data": data,
                "message": "Get successfully",
                "total_pages": total_page_number,
                "page_number": current_page,
                "total_elements": len(records)
            }),
            status=200,
            mimetype='application/json'
        )

    @http.route(
        '/api/<string:model>/<int:rec_id>',
        type='http', auth='user', methods=['GET'], csrf=False)
    def get_model_rec(self, model, rec_id, **params):
        try:
            records = request.env[model].search([])
        except KeyError as e:
            msg = f"The model `{model}` does not exist."
            res = error_response(e, msg)
            return http.Response(
                json.dumps({
                    "status": 400,
                    "data": None,
                    "message": msg
                }),
                status=200,
                mimetype='application/json'
            )

        if "query" in params:
            query = params["query"]
        else:
            query = "{*}"

        record = records.browse(rec_id).ensure_one()

        try:
            serializer = Serializer(record, query)
            data = serializer.data
        except (SyntaxError, QueryFormatError) as e:
            res = error_response(e, e.msg)
            return http.Response(
                json.dumps({
                    "status": 400,
                    "data": None,
                    "message": e.msg
                }),
                status=200,
                mimetype='application/json'
            )

        return http.Response(
            json.dumps({
                "status": 200,
                "data": data,
                "message": "Oke"
            }),
            status=200,
            mimetype='application/json'
        )

    @http.route(
        '/api/<string:model>/',
        type='json', auth="user", methods=['POST'], csrf=False)
    def post_model_data(self, model, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on POST request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_post = request.env[model]
        except KeyError:
            msg = f"The model `{model}` does not exist."
            raise exceptions.ValidationError(msg)

        if "context" in post:
            context = post["context"]
            record = model_to_post.with_context(**context).create(data)
        else:
            record = model_to_post.create(data)
        return {
            "status": 200,
            "data": {"id": record.id},
            "message": "Record created successfully"
        }

    @http.route(
        '/api/<string:model>/<int:rec_id>/',
        type='json', auth="user", methods=['PUT'], csrf=False)
    def put_model_record(self, model, rec_id, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on PUT request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_put = request.env[model]
        except KeyError:
            msg = f"The model `{model}` does not exist."
            raise exceptions.ValidationError(msg)

        if "context" in post:
            rec = model_to_put.with_context(**post["context"]).browse(rec_id).ensure_one()
        else:
            rec = model_to_put.browse(rec_id).ensure_one()

        for field in data:
            if isinstance(data[field], dict):
                operations = []
                for operation in data[field]:
                    if operation == "push":
                        operations.extend(
                            (4, rec_id, _)
                            for rec_id
                            in data[field].get("push")
                        )
                    elif operation == "pop":
                        operations.extend(
                            (3, rec_id, _)
                            for rec_id
                            in data[field].get("pop")
                        )
                    elif operation == "delete":
                        operations.extend(
                            (2, rec_id, _)
                            for rec_id in data[field].get("delete")
                        )
                    else:
                        data[field].pop(operation)  # Invalid operation

                data[field] = operations
            elif isinstance(data[field], list):
                data[field] = [(6, _, data[field])]  # Replace operation
            else:
                pass

        try:
            rec.write(data)
            return {
                "status": 200,
                "data": {"id": rec.id},
                "message": "Record updated successfully"
            }
        except Exception as e:
            return {
                "status": 500,
                "data": None,
                "message": str(e)
            }

    @http.route(
        '/api/<string:model>/',
        type='json', auth="user", methods=['PUT'], csrf=False)
    def put_model_records(self, model, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on PUT request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_put = request.env[model]
        except KeyError:
            msg = f"The model `{model}` does not exist."
            raise exceptions.ValidationError(msg)

        filters = post["filter"]

        if "context" in post:
            recs = model_to_put.with_context(**post["context"]).search(filters)
        else:
            recs = model_to_put.search(filters)

        for field in data:
            if isinstance(data[field], dict):
                operations = []
                for operation in data[field]:
                    if operation == "push":
                        operations.extend(
                            (4, rec_id, _)
                            for rec_id
                            in data[field].get("push")
                        )
                    elif operation == "pop":
                        operations.extend(
                            (3, rec_id, _)
                            for rec_id
                            in data[field].get("pop")
                        )
                    elif operation == "delete":
                        operations.extend(
                            (2, rec_id, _)
                            for rec_id in data[field].get("delete")
                        )
                    else:
                        pass  # Invalid operation

                data[field] = operations
            elif isinstance(data[field], list):
                data[field] = [(6, _, data[field])]  # Replace operation
            else:
                pass

        try:
            recs.write(data)
            return {
                "status": 200,
                "data": [{"id": rec.id} for rec in recs],
                "message": "Records updated successfully"
            }
        except Exception as e:
            return {
                "status": 500,
                "data": None,
                "message": str(e)
            }

    @http.route(
        '/api/<string:model>/<int:rec_id>/',
        type='http', auth="user", methods=['DELETE'], csrf=False)
    def delete_model_record(self, model,  rec_id, **post):
        try:
            model_to_del_rec = request.env[model]
        except KeyError as e:
            msg = "The model `%s` does not exist." % model
            res = error_response(e, msg)
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

        # TODO: Handle error raised by `ensure_one`
        rec = model_to_del_rec.browse(rec_id).ensure_one()

        try:
            is_deleted = rec.unlink()
            res = {
                "result": is_deleted
            }
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )
        except Exception as e:
            res = error_response(e, str(e))
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

    @http.route(
        '/api/<string:model>/',
        type='http', auth="user", methods=['DELETE'], csrf=False)
    def delete_model_records(self, model, **post):
        filters = json.loads(post["filter"])

        try:
            model_to_del_rec = request.env[model]
        except KeyError as e:
            msg = "The model `%s` does not exist." % model
            res = error_response(e, msg)
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

        # TODO: Handle error raised by `filters`
        recs = model_to_del_rec.search(filters)

        try:
            is_deleted = recs.unlink()
            res = {
                "result": is_deleted
            }
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )
        except Exception as e:
            res = error_response(e, str(e))
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

    @http.route(
        '/api/<string:model>/<int:rec_id>/<string:field>',
        type='http', auth="user", methods=['GET'], csrf=False)
    def get_binary_record(self, model,  rec_id, field, **post):
        try:
            request.env[model]
        except KeyError as e:
            msg = "The model `%s` does not exist." % model
            res = error_response(e, msg)
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

        rec = request.env[model].browse(rec_id).ensure_one()
        if rec.exists():
            src = getattr(rec, field).decode("utf-8")
        else:
            src = False
        return http.Response(
            src
        )
