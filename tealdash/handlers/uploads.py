import logging
import os
import uuid

from flask import request
from flask_restful import abort
from werkzeug.utils import secure_filename

from tealdash import models, redis_connection, settings
from tealdash.handlers.base import BaseResource, get_object_or_404
from tealdash.permissions import require_admin

logger = logging.getLogger(__name__)


def _get_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class DataSourceUploadListResource(BaseResource):
    @require_admin
    def get(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        uploads = models.UploadedFile.query.filter(models.UploadedFile.data_source_id == data_source.id).order_by(
            models.UploadedFile.created_at.desc()
        )
        return [upload.to_dict() for upload in uploads]

    @require_admin
    def post(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)

        if data_source.type != "duckdb":
            abort(400, message="File uploads are only supported for DuckDB data sources.")

        max_size_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
        if request.content_length and request.content_length > max_size_bytes:
            abort(413, message="File exceeds the maximum allowed size of {} MB.".format(settings.UPLOAD_MAX_SIZE_MB))

        file = request.files.get("file")
        if file is None or file.filename == "":
            abort(400, message="No file provided.")

        original_filename = secure_filename(file.filename)
        extension = _get_extension(original_filename)
        if extension not in settings.UPLOAD_ALLOWED_EXTENSIONS:
            abort(
                400,
                message="Unsupported file type '{}'. Allowed types: {}.".format(
                    extension, ", ".join(sorted(settings.UPLOAD_ALLOWED_EXTENSIONS))
                ),
            )

        display_name = (request.form.get("name") or "").strip() or None

        # Computed and checked *before* constructing the UploadedFile below: assigning
        # `data_source=` on a new UploadedFile cascades it into the session immediately
        # (via the relationship), so querying afterwards would autoflush that pending
        # insert first and the row would always collide with itself.
        candidate_view_name = models.UploadedFile.sanitize_view_name(display_name or original_filename)
        existing_view_names = {
            u.view_name for u in models.UploadedFile.query.filter(models.UploadedFile.data_source_id == data_source.id)
        }
        if candidate_view_name in existing_view_names:
            abort(
                400,
                message='A table named "{}" already exists for this data source. '
                "Choose a different name, or delete the existing one first.".format(candidate_view_name),
            )

        upload = models.UploadedFile(
            org=self.current_org,
            data_source=data_source,
            filename=original_filename,
            display_name=display_name,
            stored_filename="{}.{}".format(uuid.uuid4().hex, extension),
            content_type=file.content_type,
            created_by=self.current_user,
        )

        # Flush so org_id/data_source_id (set via the relationships above) and the
        # generated id are populated before they're used to build the storage path.
        models.db.session.add(upload)
        models.db.session.flush()

        os.makedirs(upload.directory, exist_ok=True)
        destination = upload.path
        file.save(destination)
        upload.size = os.path.getsize(destination)

        if upload.size > max_size_bytes:
            os.remove(destination)
            models.db.session.rollback()
            abort(413, message="File exceeds the maximum allowed size of {} MB.".format(settings.UPLOAD_MAX_SIZE_MB))

        models.db.session.commit()
        redis_connection.delete(data_source._schema_key)

        self.record_event(
            {
                "action": "upload_file",
                "object_id": data_source.id,
                "object_type": "datasource",
                "filename": original_filename,
            }
        )

        return upload.to_dict()


class DataSourceUploadResource(BaseResource):
    @require_admin
    def delete(self, data_source_id, upload_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        upload = get_object_or_404(models.UploadedFile.get_by_id_and_org, upload_id, self.current_org)

        if upload.data_source_id != data_source.id:
            abort(404)

        upload.delete()
        redis_connection.delete(data_source._schema_key)

        self.record_event(
            {
                "action": "delete_file",
                "object_id": data_source.id,
                "object_type": "datasource",
                "filename": upload.filename,
            }
        )

        return "", 204
