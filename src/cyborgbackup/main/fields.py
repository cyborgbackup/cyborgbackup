# Python
import json

import jsonschema.exceptions
# Django-JSONField
from django.db.models import JSONField as upstream_JSONField
# Django
from django.utils.translation import gettext_lazy as _
# jsonschema
from jsonschema import Draft4Validator


# Provide a (better) custom error message for enum jsonschema validation
def __enum_validate__(validator, enums, instance, schema):
    if instance not in enums:
        yield jsonschema.exceptions.ValidationError(
            _("'%s' is not one of ['%s']") % (instance, "', '".join(enums))
        )


Draft4Validator.VALIDATORS['enum'] = __enum_validate__


class JSONField(upstream_JSONField):

    def db_type(self, connection):
        return 'text'

    def _get_val_from_obj(self, obj):
        return self.value_from_object(obj)

    def from_db_value(self, value, expression, connection):
        if value in {'', None} and not self.null:
            return {}
        if isinstance(value, str):
            return json.loads(value)
        return value
