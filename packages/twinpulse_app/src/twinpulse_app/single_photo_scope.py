# SPDX-License-Identifier: Apache-2.0
"""One actual dispatch maximum, independent of a multi-stage generation policy."""
from threading import RLock
from .product_inference import ProductInferenceScope
from twinpulse_provider.errors import ProviderConfigurationError


class SinglePhotoLedger:
    product_usage=True
    def __init__(self,ledger):self.ledger=ledger;self.lock=RLock();self.used=False
    @property
    def state(self):return self.ledger.state
    def reserve(self,body):
        with self.lock:
            if self.used:raise ProviderConfigurationError('ENVIRONMENT_PHOTO_ONE_CALL_ONLY')
            self.used=True  # Unknown/error outcomes do not restore permission.
            return self.ledger.reserve(body)
    def settle(self,*args,**kwargs):return self.ledger.settle(*args,**kwargs)


class SinglePhotoScope(ProductInferenceScope):
    def bind(self,*args,**kwargs):return SinglePhotoLedger(super().bind(*args,**kwargs))
