#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2020 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# Author: Komal Thareja (kthare10@renci.org)
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import base64, json, time

@dataclass(frozen=True)
class AuthProvider:
    id_token: str
    refresh_token: Optional[str] = None

    @staticmethod
    def from_token(id_token: str, refresh_token: Optional[str] = None) -> "AuthProvider":
        if not id_token or not isinstance(id_token, str):
            raise ValueError("id_token must be a non-empty string")
        return AuthProvider(id_token=id_token, refresh_token=refresh_token)

    @staticmethod
    def _b64url_decode(seg: str) -> bytes:
        # len % 4 padding fix for urlsafe base64
        return base64.urlsafe_b64decode(seg + "=" * ((4 - len(seg) % 4) % 4))

    def decode_jwt_claims(self) -> Dict[str, Any]:
        # Best-effort decode (no signature verification here)
        try:
            parts = self.id_token.split(".")
            if len(parts) != 3:
                return {}
            payload_bytes = self._b64url_decode(parts[1])
            return json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            return {}

    def is_expired(self, skew_seconds: int = 60) -> bool:
        claims = self.decode_jwt_claims()
        exp = claims.get("exp")
        if exp is None:
            # If no exp, let upstream API decide; treat as not expired.
            return False
        # Compare to current epoch
        return int(time.time()) >= int(exp) - skew_seconds
