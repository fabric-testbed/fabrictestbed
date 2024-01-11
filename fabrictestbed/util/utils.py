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
#
#
# Author: Komal Thareja (kthare10@renci.org)
#
import hashlib
import json


class Utils:
    @staticmethod
    def generate_sha256(*, token: str):
        """
        Generate SHA 256 for a token
        @param token token string
        """
        # Create a new SHA256 hash object
        sha256_hash = hashlib.sha256()

        # Convert the string to bytes and update the hash object
        sha256_hash.update(token.encode('utf-8'))

        # Get the hexadecimal representation of the hash
        sha256_hex = sha256_hash.hexdigest()

        return sha256_hex

    @staticmethod
    def extract_error_message(*, exception):
        body = exception
        if hasattr(exception, "body"):
            body = exception.body
        try:
            response_body = json.loads(body)
            errors = response_body.get("errors")
            if errors and len(errors) > 0:
                return f"{errors[0].get('message')} - {errors[0].get('details')}"
        except Exception:
            return str(exception)
        return str(exception)