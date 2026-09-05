"""Read machine-local setup without storing personal paths in source control."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_config():
    path = Path(os.environ.get('WARNO10V10_CONFIG', ROOT / 'config.local.json'))
    if not path.is_file():
        raise RuntimeError('Run Setup.ps1 first to select your WARNO executable and profile.')
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    for key in ('game_exe', 'profile', 'python_exe'):
        value = settings.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f'Setup contains an invalid {key}; run Setup.ps1 again.')
    if Path(settings['game_exe']).name.lower() != 'warno.exe':
        raise ValueError('The configured executable must be WARNO.exe.')
    if Path(settings['profile']).name.lower() != 'profile.profile2':
        raise ValueError('The configured profile must be PROFILE.profile2.')
    return settings
