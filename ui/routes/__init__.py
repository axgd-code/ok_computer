from .actions_routes import create_actions_blueprint
from .core_routes import create_core_blueprint
from .extensions_routes import create_extensions_blueprint
from .packages_routes import create_packages_blueprint
from .preferences_routes import create_preferences_blueprint


def register_blueprints(app, state):
    app.register_blueprint(create_core_blueprint(state))
    app.register_blueprint(create_preferences_blueprint(state))
    app.register_blueprint(create_packages_blueprint(state))
    app.register_blueprint(create_extensions_blueprint(state))
    app.register_blueprint(create_actions_blueprint(state))
