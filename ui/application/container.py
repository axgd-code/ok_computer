from dataclasses import dataclass

from application.use_cases.actions_use_cases import ActionsUseCases
from application.use_cases.core_use_cases import CoreUseCases
from application.use_cases.extensions_use_cases import ExtensionsUseCases
from application.use_cases.packages_use_cases import PackagesUseCases
from application.use_cases.preferences_use_cases import PreferencesUseCases
from infrastructure.extension_search_gateway import ExtensionSearchGateway
from infrastructure.package_search_gateway import PackageSearchGateway


@dataclass
class UseCaseContainer:
    actions: ActionsUseCases
    core: CoreUseCases
    extensions: ExtensionsUseCases
    packages: PackagesUseCases
    preferences: PreferencesUseCases


def build_use_cases(state):
    package_search_gateway = PackageSearchGateway()
    extension_search_gateway = ExtensionSearchGateway()
    return UseCaseContainer(
        actions=ActionsUseCases(state),
        core=CoreUseCases(state),
        extensions=ExtensionsUseCases(state, search_port=extension_search_gateway),
        packages=PackagesUseCases(state, search_port=package_search_gateway),
        preferences=PreferencesUseCases(state),
    )
