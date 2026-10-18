# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Provider-bound key metadata; secrets remain in the OS credential store."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from threading import RLock
from typing import Callable, Mapping
from uuid import UUID, uuid4

from .credentials import CredentialStore, WindowsCredentialStore
from .settings import JsonProviderSettingsStore, ProviderSettings, provider_settings_preset


class KeyRegistryError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


class KeyRegistry:
    """No network activity, key export, arbitrary credential targets or origins."""
    def __init__(self, settings: JsonProviderSettingsStore, legacy: CredentialStore,
                 factory: Callable[[str], CredentialStore] = WindowsCredentialStore):
        self.settings, self.legacy, self.factory = settings, legacy, factory
        self.path = settings.path.with_name('provider_keys.json')
        self.lock = RLock()
        initial = settings.load().validated()
        self.initial = initial if initial.credential_ref == legacy.target_name else None

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return ([{'id': 'legacy', 'name': 'Existing saved key', 'settings': self.initial.to_dict()}]
                    if self.initial is not None else [])
        try:
            if self.path.stat().st_size > 128 * 1024:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if set(data) != {'schema_version', 'entries'} or data['schema_version'] != '1.0':
                raise ValueError()
            entries = data['entries']
            if not isinstance(entries, list) or len(entries) > 32:
                raise ValueError()
            ids = set()
            for entry in entries:
                if set(entry) != {'id', 'name', 'settings'} or entry['id'] in ids:
                    raise ValueError()
                ids.add(entry['id'])
                self._name(entry['name'])
                value = ProviderSettings.from_dict(entry['settings'])
                if entry['id'] == 'legacy':
                    if value.credential_ref != self.legacy.target_name:
                        raise ValueError()
                else:
                    if str(UUID(entry['id'])) != entry['id']:
                        raise ValueError()
                    expected = f'TwinPulse/ProviderKeys/{value.provider_profile}/{entry["id"]}'
                    if value.credential_ref != expected:
                        raise ValueError()
                    preset = provider_settings_preset(value.provider_profile, credential_ref=expected)
                    if value.binding_identity != preset.binding_identity or value.base_url != preset.base_url:
                        raise ValueError()
            return entries
        except Exception:
            raise KeyRegistryError('key_registry_corrupt', '키 목록을 읽지 못했습니다. 원본은 보존되었습니다.', 500) from None

    @staticmethod
    def _name(name: object) -> str:
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise KeyRegistryError('key_name_invalid', '키 이름은 1~80자의 일반 텍스트로 입력하세요.')
        return name.strip()

    def _save(self, entries: list[dict]) -> None:
        temporary = self.path.with_name(f'.{self.path.name}.{uuid4().hex}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open('xb') as stream:
                stream.write(json.dumps({'schema_version': '1.0', 'entries': entries}, ensure_ascii=False).encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def _store(self, entry: dict) -> CredentialStore:
        ref = entry['settings']['credential_ref']
        return self.legacy if entry['id'] == 'legacy' else self.factory(ref)

    def resolve(self, value: ProviderSettings) -> CredentialStore:
        with self.lock:
            for entry in self._entries():
                registered = ProviderSettings.from_dict(entry['settings'])
                if registered.credential_ref == value.credential_ref:
                    if registered.binding_identity != value.binding_identity or registered.base_url != value.base_url:
                        raise KeyRegistryError('credential_binding_mismatch', '이 키는 다른 공급자 또는 주소로 전송할 수 없습니다.', 409)
                    return self._store(entry)
            raise KeyRegistryError('credential_reference_mismatch', '등록된 공급자별 키를 선택하세요.', 409)

    def settings_for_entry(self, identity: str) -> ProviderSettings:
        """Explicit stage selection without changing the active/default provider."""
        with self.lock:
            for entry in self._entries():
                if entry['id'] == identity:
                    return ProviderSettings.from_dict(entry['settings'])
            raise KeyRegistryError('key_entry_missing', '등록된 키 항목을 찾지 못했습니다.', 404)

    def state(self) -> dict:
        with self.lock:
            active = self.settings.load().validated()
            result = []
            for entry in self._entries():
                value = ProviderSettings.from_dict(entry['settings'])
                try:
                    configured = self._store(entry).is_configured()
                except Exception:
                    raise KeyRegistryError('credential_status_failed', '보안 저장소 상태를 읽지 못했습니다.', 500) from None
                result.append({'id': entry['id'], 'name': entry['name'], 'provider_profile': value.provider_profile,
                               'model_id': value.model_id, 'base_url': value.base_url, 'configured': configured,
                               'active': value.credential_ref == active.credential_ref,
                               'removable': entry['id'] != 'legacy'})
            from .stage_routing import StageRoutingSettings
            stages = StageRoutingSettings(self).state(result)
            route = stages['route']
            pinned = {route[stage]['key_id'] for stage in ('observer', 'planner')} if route else set()
            for item in result:
                item['stage_selected'] = item['id'] in pinned
                item['removable'] = item['removable'] and item['id'] not in pinned
            return {'schema_version': '1.0', 'entries': result, 'network_called': False,
                    'stage_routing': stages,
                    'note': 'Save stage choices above. Key registration or settings save does not verify authentication or generation quality.'}

    def register(self, body: Mapping[str, object]) -> dict:
        with self.lock:
            if set(body) != {'name', 'provider_profile', 'model_id', 'api_key'}:
                raise KeyRegistryError('request_shape_invalid', '키 등록 요청 형식이 잘못되었습니다.')
            name = self._name(body['name'])
            profile, model, secret = body['provider_profile'], body['model_id'], body['api_key']
            if not isinstance(profile, str) or not isinstance(model, str):
                raise KeyRegistryError('request_value_invalid', '공급자와 모델을 선택하세요.')
            if profile not in {'openai', 'nebius_token_factory', 'nebius_site_v2'}:
                raise KeyRegistryError('provider_settings_invalid', '지원되는 공급자를 선택하세요.')
            if not isinstance(secret, str) or not secret.strip() or len(secret.encode('utf-16-le')) > 2560 or any(ord(c) < 32 for c in secret):
                raise KeyRegistryError('api_key_invalid', '비어 있거나 너무 긴 키 또는 줄바꿈이 포함된 키는 저장할 수 없습니다.')
            entries = self._entries()
            if len(entries) >= 32:
                raise KeyRegistryError('key_list_full', '최대 32개의 키를 저장할 수 있습니다.', 409)
            identifier = str(uuid4())
            try:
                value = provider_settings_preset(profile, credential_ref=f'TwinPulse/ProviderKeys/{profile}/{identifier}')
                if profile == 'openai':
                    value = replace(value, model_id=model).validated()
                elif model != value.model_id:
                    raise ValueError()
            except ValueError:
                raise KeyRegistryError('provider_settings_invalid', '지원되는 공급자와 모델 설정을 사용하세요.') from None
            entry = {'id': identifier, 'name': name, 'settings': value.to_dict()}
            store = self._store(entry)
            try:
                store.save(secret)
            except Exception:
                raise KeyRegistryError('credential_save_failed', '키를 Windows 보안 저장소에 저장하지 못했습니다.', 500) from None
            try:
                self._save(entries + [entry])
            except Exception:
                try:
                    store.delete()
                except Exception:
                    raise KeyRegistryError('key_registration_rollback_failed', '목록 저장 실패 후 새 키 정리가 실패했습니다. 기존 키는 변경하지 않았습니다.', 500) from None
                raise KeyRegistryError('key_registry_save_failed', '키 목록을 저장하지 못했습니다. 새 키는 제거했고 기존 키는 보존했습니다.', 500) from None
            return self.state()

    def entry(self, identifier: object) -> dict:
        for entry in self._entries():
            if entry['id'] == identifier:
                return entry
        raise KeyRegistryError('key_not_found', '선택한 키가 목록에 없습니다.', 404)

    def select(self, identifier: object, changed: Callable[[], object]) -> dict:
        with self.lock:
            from .stage_routing import StageRoutingSettings
            if StageRoutingSettings(self).load() is not None:
                raise KeyRegistryError('stage_routing_active', '단계별 조합을 사용 중입니다. 단일 공급자 모드로 전환한 뒤 키를 선택하세요.', 409)
            entry = self.entry(identifier)
            value = ProviderSettings.from_dict(entry['settings'])
            try:
                if not self._store(entry).is_configured():
                    raise KeyRegistryError('key_missing', '보안 저장소에 키가 없습니다. 새 키를 등록하세요.', 409)
                previous = self.settings.load()
                # Persist the old legacy binding before selecting another key.
                self._save(self._entries())
                self.settings.save(value)
            except KeyRegistryError:
                raise
            except Exception:
                raise KeyRegistryError('provider_switch_storage_failed', '설정 저장 또는 복구에 실패했습니다. 현재 설정을 새로 확인하세요.', 500) from None
        # Do not retain registry while calling the workflow (snapshot uses the
        # opposite lock order). API settings lock serializes this transaction.
        try:changed()
        except Exception:
            with self.lock:
                if self.settings.load()!=value:
                    raise KeyRegistryError('provider_switch_superseded','더 새 공급자 설정을 덮지 않았습니다. 현재 설정을 확인하세요.',409) from None
                try:self.settings.save(previous)
                except Exception:
                    raise KeyRegistryError('provider_switch_recovery_failed','설정 및 복구 상태를 확인하지 못했습니다.',500) from None
            try:changed()
            except Exception:
                raise KeyRegistryError('provider_switch_recovery_failed','이전 설정은 저장했지만 게이트웨이 복구를 확인하지 못했습니다.',500) from None
            raise KeyRegistryError('provider_switch_failed','공급자 전환에 실패해 이전 설정으로 되돌렸습니다.',409) from None
        return self.state()

    def remove(self, identifier: object) -> dict:
        with self.lock:
            entry = self.entry(identifier)
            from .stage_routing import StageRoutingSettings
            route = StageRoutingSettings(self).load()
            pinned = {route[stage]['key_id'] for stage in ('observer', 'planner')} if route else set()
            if identifier in pinned or identifier == 'legacy' or entry['settings']['credential_ref'] == self.settings.load().credential_ref:
                raise KeyRegistryError('key_delete_locked', '기존 보존 키 또는 현재 사용 중인 키는 삭제할 수 없습니다.', 409)
            # Remove the secret first: failure leaves the recoverable metadata.
            try:
                self._store(entry).delete()
                self._save([item for item in self._entries() if item['id'] != identifier])
            except Exception:
                raise KeyRegistryError('key_delete_failed', '키 삭제가 완료되지 않았습니다. 목록을 새로 확인하세요.', 500) from None
            return self.state()
