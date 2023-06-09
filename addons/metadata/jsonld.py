import json
import logging

from osf.models.metaschema import RegistrationSchema


logger = logging.getLogger(__name__)


def _convert_metadata_item_to_json_ld_entity(item):
    schema = item['schema']
    registration_schema = RegistrationSchema.objects.get(_id=schema)
    return {
        '@type': 'FileMetadata',
        'active': item.get('active', False),
        'schema': registration_schema.name,
        'version': registration_schema.schema_version,
        'data': json.dumps(item['data']),
    }

def convert_metadata_to_json_ld_entities(metadata):
    return [
        _convert_metadata_item_to_json_ld_entity(item)
        for item in metadata['items']
    ]

def convert_json_ld_entity_to_metadata_item(props):
    if props['@type'] != 'FileMetadata':
        raise ValueError(f'Unexpected type: {props["@type"]}')
    registration_schema = RegistrationSchema.objects.filter(
        name=props['schema'],
    ).order_by('-schema_version').first()
    if registration_schema is None:
        return None
    return {
        'active': props.get('active', False),
        'schema': registration_schema._id,
        'data': json.loads(props['data']),
    }
