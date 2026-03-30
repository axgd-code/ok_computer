from domain.models import ApiResult
from shared.errors import NotFoundError, ValidationError


class ActionsUseCases:
    def __init__(self, state):
        self.state = state

    def _start_init_job(self, target, *job_args):
        import threading
        import uuid

        job_id = str(uuid.uuid4())
        with self.state.INIT_JOBS_LOCK:
            self.state.INIT_JOBS[job_id] = {
                'done': False,
                'ok': None,
                'progress': 0,
                'step': 'queued',
                'message': 'Queued...',
            }
        thread = threading.Thread(target=target, args=(job_id, *job_args), daemon=True)
        thread.start()
        return ApiResult({'status': 'started', 'jobId': job_id}, status=200)

    def run_update(self, timeout):
        result = self.state._run_update_script(timeout=timeout)
        if result.get('error'):
            return ApiResult(result, status=500)
        return ApiResult(result, status=200)

    def run_install(self, app_name):
        if not app_name:
            raise ValidationError('missing app name')
        result, status = self.state._actions_service().run_install_action(app_name)
        return ApiResult(result, status=status)

    def run_import_installed(self):
        result, status = self.state._actions_service().run_import_installed_action()
        return ApiResult(result, status=status)

    def init_from_zip(self, zip_path_raw):
        if not zip_path_raw:
            raise ValidationError('zipPath is required')
        from pathlib import Path

        zip_path = Path(zip_path_raw).expanduser()
        if not zip_path.exists() or not zip_path.is_file():
            raise NotFoundError(f'Zip file not found: {zip_path}')

        return self._start_init_job(self.state._run_init_from_zip_job, str(zip_path))

    def init_from_shared(self):
        return self._start_init_job(self.state._run_init_from_shared_job)

    def init_status(self, job_id):
        with self.state.INIT_JOBS_LOCK:
            status = self.state.INIT_JOBS.get(job_id)
        if not status:
            raise NotFoundError('job not found')
        return ApiResult(status, status=200)
