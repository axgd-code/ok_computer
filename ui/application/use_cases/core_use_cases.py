from domain.models import ApiResult
from shared.errors import ValidationError


class CoreUseCases:
    def __init__(self, state):
        self.state = state

    def open_path(self, target):
        if not target:
            raise ValidationError('no path provided')
        from pathlib import Path
        import platform
        import subprocess

        path = Path(target)
        if platform.system() == 'Darwin':
            subprocess.Popen(['open', '-R', str(path)], close_fds=True)
        elif platform.system() == 'Windows':
            subprocess.Popen(['explorer', '/select,', str(path)], close_fds=True)
        else:
            subprocess.Popen(['xdg-open', str(path.parent)], close_fds=True)
        return ApiResult({'status': 'ok'}, status=200)

    def sync_scripts(self):
        copied = self.state.ensure_user_scripts_available()
        return ApiResult(
            {
                'status': 'ok',
                'copied_count': len(copied),
                'copied': copied,
                'scripts_dir': str(self.state.USER_SRC_DIR),
            },
            status=200,
        )
