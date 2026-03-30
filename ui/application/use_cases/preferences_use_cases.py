from domain.models import ApiResult


class PreferencesUseCases:
    def __init__(self, state):
        self.state = state

    def get_system_settings(self):
        return ApiResult(self.state.parse_system_settings_conf(), status=200)

    def update_system_settings(self, lines):
        conf_file = self.state._config_target_path('system_settings.conf')
        conf_file.parent.mkdir(parents=True, exist_ok=True)
        conf_file.write_text('\n'.join(lines) + '\n')
        return ApiResult({'status': 'ok', 'path': str(conf_file)}, status=200)

    def get_env(self):
        return ApiResult(self.state.load_env_dict(), status=200)

    def update_env(self, data):
        from dotenv import set_key

        self.state._ensure_env_local_complete()
        for key, value in data.items():
            set_key(str(self.state.ENV_LOCAL), key, str(value))
        self.state._ensure_env_local_complete()
        self.state._sync_env_to_repo_if_possible()
        self.state.app.logger.info('Settings saved to %s (%d keys)', self.state.ENV_LOCAL, len(data))
        return ApiResult({'status': 'ok', 'path': str(self.state.ENV_LOCAL)}, status=200)
