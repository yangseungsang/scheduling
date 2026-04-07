"""Synchronization service — merges external provider data into local models."""
from app.features.schedule.models import version, task


class SyncService:

    @staticmethod
    def sync_versions(provider):
        """Sync versions from provider. Returns {added, updated, deactivated}."""
        external = provider.get_versions()
        external_ids = {v['id'] for v in external}
        existing = {v['id']: v for v in version.get_all()}
        added = updated = deactivated = 0

        for ext in external:
            if ext['id'] in existing:
                version.update(ext['id'], name=ext['name'],
                               description=ext.get('description', ''),
                               is_active=True)
                updated += 1
            else:
                version.create(name=ext['name'],
                               description=ext.get('description', ''),
                               id=ext['id'])
                added += 1

        for vid, v in existing.items():
            if vid not in external_ids and v.get('is_active', True):
                version.patch(vid, is_active=False)
                deactivated += 1

        return {'added': added, 'updated': updated, 'deactivated': deactivated}

    @staticmethod
    def sync_test_data(provider, version_id=None):
        """Sync test data from provider. Returns {added, updated, cancelled, warnings}."""
        if version_id:
            external = provider.get_test_data(version_id)
        else:
            external = provider.get_test_data_all()

        external_keys = set()
        added = updated = cancelled = 0
        warnings = []

        for item in external:
            key = item['section_name']
            external_keys.add(key)
            existing = task.get_by_external_key(key)

            identifiers = item.get('identifiers', [])
            est_minutes = sum(i.get('estimated_minutes', 0) for i in identifiers)

            if existing:
                task.patch(existing['id'],
                           test_list=identifiers,
                           estimated_minutes=est_minutes,
                           section_name=item['section_name'])
                updated += 1
            else:
                task.create(
                    procedure_id='EXT-' + str(len(task.get_all()) + 1).zfill(3),
                    assignee_ids=[],
                    location_id='',
                    section_name=item['section_name'],
                    procedure_owner='',
                    test_list=identifiers,
                    estimated_minutes=est_minutes,
                    source='external',
                    external_key=key,
                )
                added += 1

        # Cancel external tasks whose key no longer exists in provider
        for t in task.get_all():
            if (t.get('source') == 'external'
                    and t.get('external_key')
                    and t['external_key'] not in external_keys
                    and t.get('status') != 'cancelled'):
                task.patch(t['id'], status='cancelled')
                cancelled += 1

        return {'added': added, 'updated': updated,
                'cancelled': cancelled, 'warnings': warnings}
