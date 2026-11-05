from django.core.exceptions import ValidationError

def validate_attribute_length(value):
    if len(value) > 20:
        raise ValidationError("Attribute is too long")