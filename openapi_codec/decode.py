from coreapi import Document, Link, Field
from coreapi.compat import string_types, urlparse
from coreapi.exceptions import ParseError


def _parse_document(data, base_url=None):
    schema_url = base_url
    base_url = _get_document_base_url(data, base_url)
    info = _get_dict(data, 'info')
    title = _get_string(info, 'title')
    paths = _get_dict(data, 'paths')
    content = {}
    for path in paths.keys():
        url = urlparse.urljoin(base_url, path.lstrip('/'))
        spec = _get_dict(paths, path)
        default_parameters = get_dicts(_get_list(spec, 'parameters'))
        for action in spec.keys():
            action = action.lower()
            if action not in ('get', 'put', 'post', 'delete', 'options', 'head', 'patch'):
                continue
            operation = _get_dict(spec, action)

            # Determine any fields on the link.
            fields = []
            parameters = get_dicts(_get_list(operation, 'parameters', default_parameters), dereference_using=data)
            for parameter in parameters:
                name = _get_string(parameter, 'name')
                location = _get_string(parameter, 'in')
                required = _get_bool(parameter, 'required', default=(location == 'path'))
                if location == 'body':
                    schema = _get_dict(parameter, 'schema', dereference_using=data)
                    expanded = _expand_schema(schema)
                    if expanded is not None:
                        expanded_fields = [
                            Field(name=field_name, location='form', required=is_required)
                            for field_name, is_required in expanded
                            if not any([field.name == name for field in fields])
                        ]
                        fields += expanded_fields
                    else:
                        field = Field(name=name, location='body', required=True)
                        fields.append(field)
                else:
                    field = Field(name=name, location=location, required=required)
                    fields.append(field)
            link = Link(url=url, action=action, fields=fields)

            # Add the link to the document content.
            tags = get_strings(_get_list(operation, 'tags'))
            operation_id = _get_string(operation, 'operationId')
            if tags:
                for tag in tags:
                    if tag not in content:
                        content[tag] = {}
                    content[tag][operation_id] = link
            else:
                content[operation_id] = link

    return Document(url=schema_url, title=title, content=content)


def _get_document_base_url(data, base_url=None):
    """
    Get the base url to use when constructing absolute paths from the
    relative ones provided in the schema defination.
    """
    prefered_schemes = ['http', 'https']
    if base_url:
        url_components = urlparse.urlparse(base_url)
        default_host = url_components.netloc
        default_scheme = url_components.scheme
    else:
        default_host = ''
        default_scheme = None

    host = _get_string(data, 'host', default=default_host)
    path = _get_string(data, 'basePath', default='/')

    if not host:
        # No host is provided, and we do not have an initial URL.
        return path.strip('/') + '/'

    schemes = _get_list(data, 'schemes')

    if not schemes:
        # No schemes provided, use the initial URL, or a fallback.
        scheme = default_scheme or prefered_schemes[0]
    elif default_scheme in schemes:
        # Schemes provided, the initial URL matches one of them.
        scheme = default_scheme
    else:
        # Schemes provided, the initial URL does not match, pick a fallback.
        for scheme in prefered_schemes:
            if scheme in schemes:
                break
        else:
            raise ParseError('Unsupported transport schemes "%s"' % schemes)

    return '%s://%s/%s/' % (scheme, host, path.strip('/'))


def _expand_schema(schema):
    """
    When an OpenAPI parameter uses `in="body"`, and the schema type is "object",
    then we expand out the parameters of the object into individual fields.
    """
    schema_type = schema.get('type')
    schema_properties = _get_dict(schema, 'properties')
    schema_required = _get_list(schema, 'required')
    if ((schema_type == ['object']) or (schema_type == 'object')) and schema_properties:
        return [
            (key, key in schema_required)
            for key in schema_properties.keys()
        ]
    return None


# Helper functions to get an expected type from a dictionary.

def dereference(lookup_string, struct):
    """
    Dereference a JSON pointer.
    http://tools.ietf.org/html/rfc6901
    """
    keys = lookup_string.strip('#/').split('/')
    node = struct
    for key in keys:
        node = _get_dict(node, key)
    return node


def is_json_pointer(value):
    return isinstance(value, dict) and ('$ref' in value) and (len(value) == 1)


def _get_string(item, key, default=''):
    value = item.get(key)
    return value if isinstance(value, string_types) else default


def _get_dict(item, key, default={}, dereference_using=None):
    value = item.get(key)
    if isinstance(value, dict):
        if dereference_using and is_json_pointer(value):
            return dereference(value['$ref'], dereference_using)
        return value
    return default.copy()


def _get_list(item, key, default=[]):
    value = item.get(key)
    return value if isinstance(value, list) else list(default)


def _get_bool(item, key, default=False):
    value = item.get(key)
    return value if isinstance(value, bool) else default


# Helper functions to get an expected type from a list.

def get_dicts(item, dereference_using=None):
    ret = [value for value in item if isinstance(value, dict)]
    if dereference_using:
        return [
            dereference(value['$ref'], dereference_using) if is_json_pointer(value) else value
            for value in ret
        ]
    return ret


def get_strings(item):
    return [value for value in item if isinstance(value, string_types)]
