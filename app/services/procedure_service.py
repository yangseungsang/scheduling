from app.json_store import read_json

FILENAME = 'procedures.json'


def lookup(procedure_id):
    """Look up procedure info by ID.

    Currently reads from mock data file.
    In production, replace with external API call.
    """
    procedures = read_json(FILENAME)
    for p in procedures:
        if p['procedure_id'] == procedure_id:
            return {
                'section_name': p['section_name'],
                'procedure_owner': p['procedure_owner'],
                'test_list': p['test_list'],
            }
    return None
