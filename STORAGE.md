# Self-hosted school storage

Replaces Cloudinary. Every uploaded asset now lives on our own server, in a
folder owned by the school that uploaded it, and is indexed in the `school_file`
table so usage can be reported and quotas enforced.

## Layout

```
<SCHOOL_STORAGE_DIR>/
    school_<id>/
        stories/audio/          narration for audiobook pages
        stories/images/         audiobook page illustrations
        books/covers/           book + audiobook cover images
        books/files/            story PDFs
        packs/images/           pack cover images
        general/                avatars, public-page logos and covers, misc
    platform/                   super-admin assets, same sub-tree
```

`platform/` holds anything not owned by one school (platform books, pack
templates, super-admin avatars). It is not charged to any school's quota.

## Server configuration

The backend lives at `/var/www/html/iread/backend`, so with no configuration the
storage root resolves to `/var/www/html/iread/backend/storage` — correct only if
the service is started with that as its working directory. Set both values
explicitly in `/var/www/html/iread/backend/.env` rather than relying on that:

```ini
# Absolute path — must be persistent, backed-up disk. Losing this directory
# loses every image, PDF and audio file on the platform.
SCHOOL_STORAGE_DIR=/var/www/html/iread/backend/storage

# Origin the stored URLs are built from. These URLs are written into the
# database (book.img, pack.img, user.img, ...) and read by all four frontends,
# so they must be absolute and must not change afterwards — changing it breaks
# every URL already stored.
PUBLIC_MEDIA_BASE_URL=https://api.iread.education

# Default per-school allowance in MB. Override per school from the super-admin
# storage page (writes shcool.storage_quota_mb).
SCHOOL_STORAGE_QUOTA_MB=5120

# Per-file ceilings.
MAX_MEDIA_IMAGE_UPLOAD_MB=10
MAX_MEDIA_AUDIO_UPLOAD_MB=50
MAX_MEDIA_DOCUMENT_UPLOAD_MB=50
```

The directory must be writable by the user the Flask app runs as:

```bash
mkdir -p /var/www/html/iread/backend/storage
chown -R www-data:www-data /var/www/html/iread/backend/storage
chmod 755 /var/www/html/iread/backend/storage
```

`client_max_body_size` in nginx has to be at least the largest
`MAX_MEDIA_*_UPLOAD_MB` value, or a large audio upload is rejected by nginx
before Flask ever sees it (a 413 with an HTML body, which the dashboards cannot
parse into a message):

```nginx
client_max_body_size 60M;
```

### Optional: let nginx serve the files

`/media/<path>` is served by Flask via `send_file`. That is correct but spends a
worker on every image. Because the route is public and the paths map 1:1 onto
disk, nginx can serve them directly instead:

```nginx
location /media/ {
    alias /var/www/html/iread/backend/storage/;
    add_header Cache-Control "public, max-age=31536000, immutable";
    try_files $uri =404;
}
```

Stored filenames carry a uuid, so this exposes nothing that the Flask route did
not already. Keep the Flask route registered as the fallback.

## Rollout order

1. `flask db upgrade` — creates `school_file`, adds `shcool.storage_quota_mb`,
   and widens `session.img` from 100 to 500 characters (a local media URL is
   ~115 characters and would otherwise be truncated into a broken link).
2. Set the `.env` values above and restart the backend.
3. `python scripts/index_school_storage.py --dry-run` — reports what is on disk
   but not yet indexed, including the two legacy upload trees. Run without
   `--dry-run` when the report looks right.
4. `python scripts/migrate_cloudinary_to_local.py --dry-run` — lists every
   database column still pointing at Cloudinary. Run without `--dry-run` to
   download those images into the owning school's folder and rewrite the
   columns. **Until this runs, existing images are still served by Cloudinary.**
5. Deploy the dashboard build (Cloudinary removed from the frontend).

### Verifying step 4 finished

```sql
SELECT 'book' t, COUNT(*) FROM book  WHERE img LIKE '%cloudinary%'
UNION ALL SELECT 'pack', COUNT(*) FROM pack WHERE img LIKE '%cloudinary%'
UNION ALL SELECT 'pack_template', COUNT(*) FROM pack_template WHERE img LIKE '%cloudinary%'
UNION ALL SELECT 'user', COUNT(*) FROM user WHERE img LIKE '%cloudinary%'
UNION ALL SELECT 'session', COUNT(*) FROM session WHERE img LIKE '%cloudinary%'
UNION ALL SELECT 'public_page', COUNT(*) FROM school_public_page
    WHERE logo LIKE '%cloudinary%' OR cover_image LIKE '%cloudinary%'
       OR CAST(sections AS CHAR) LIKE '%cloudinary%'
       OR CAST(draft_data AS CHAR) LIKE '%cloudinary%';
```

All counts must be zero. Only then is the Cloudinary account safe to close.

## Known gaps

- **Notification category images are not covered.** They live in the separate
  notification microservice (MongoDB), not this database, so
  `migrate_cloudinary_to_local.py` cannot reach them. The dashboard now uploads
  them to local storage, but images stored before that still point at
  Cloudinary and need the same treatment through that service's own API.
- **Archived audiobooks keep their files.** Deleting an audiobook is a soft
  delete (`active = False`); the audio and images stay on disk and keep counting
  against the school's quota. That is pre-existing behaviour, not introduced
  here — the storage manager now at least makes those files visible so an admin
  can reclaim the space deliberately.
- **Replacing an image does not delete the old file.** Intentional: the storage
  manager exists so one image can be reused across several books and packs, and
  auto-deleting on replace would pull a shared asset out from under the others.
  Space is reclaimed explicitly from the storage page, which warns when a file is
  still referenced.

## Operational tasks

```bash
# Reconcile the index with the filesystem (safe, re-runnable).
python scripts/index_school_storage.py --dry-run
python scripts/index_school_storage.py

# Release quota held by rows whose file was deleted on the server by hand.
python scripts/index_school_storage.py --prune

# One school only.
python scripts/index_school_storage.py --school 12
```
