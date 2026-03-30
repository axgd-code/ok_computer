from domain.models import ApiResult
from shared.errors import ValidationError
from application.ports import PackageSearchPort


class PackagesUseCases:
    def __init__(self, state, search_port: PackageSearchPort | None = None):
        self.state = state
        self.search_port = search_port

    def list_packages(self, include_availability=False):
        packages = self.state.read_packages()
        if include_availability:
            packages = self.state.PACKAGES_SERVICE.enrich_packages_with_availability(packages)
        else:
            for package in packages:
                package['apt_available'] = False
                package['linux'] = '-'
        return ApiResult(packages, status=200)

    def check_package(self, appname):
        if not appname:
            raise ValidationError('missing app parameter')
        result = {'app': appname, 'available': False, 'sources': {}}
        try:
            homebrew = self.state.check_homebrew(appname)
            result['sources']['homebrew'] = homebrew
            result['available'] = result['available'] or bool(homebrew)
        except Exception:
            result['sources']['homebrew'] = False
        try:
            chocolatey = self.state.check_chocolatey(appname)
            result['sources']['chocolatey'] = chocolatey
            result['available'] = result['available'] or bool(chocolatey)
        except Exception:
            result['sources']['chocolatey'] = False
        try:
            debian = self.state.check_debian(appname)
            result['sources']['debian'] = debian
            result['available'] = result['available'] or bool(debian)
        except Exception:
            result['sources']['debian'] = False
        return ApiResult(result, status=200)

    def update_package(self, app_name):
        if not app_name:
            raise ValidationError('missing app')
        result, status = self.state._actions_service().run_package_update(app_name)
        return ApiResult(result, status=status)

    def remove_package(self, app_name, run_uninstall=True):
        if not app_name:
            raise ValidationError('missing app')
        result, status = self.state._actions_service().run_package_remove(app_name, run_uninstall=run_uninstall)
        return ApiResult(result, status=status)

    def search_packages(self, query):
        if not query:
            raise ValidationError('missing q parameter')
        if self.search_port is None:
            return ApiResult({'query': query, 'results': []}, status=200)
        payload = self.search_port.search(query, self.state._urlquote)
        return ApiResult(payload, status=200)
