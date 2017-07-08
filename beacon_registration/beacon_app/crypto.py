import base64
import string

from Crypto import Random
from Crypto.Cipher import AES
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from typing import Dict

from django.contrib.auth.models import User


class PasswordCrypto:

    def __init__(self, user: User):
        self.user = user

        split_pw = self.split_password()
        self.key = base64.b64decode(split_pw['hash'])

    @staticmethod
    def _pkcs7_pad(plaintext: string) -> string:
        block_size = AES.block_size
        pad_length = block_size - (len(plaintext) % block_size)
        return plaintext + chr(pad_length) * pad_length

    @staticmethod
    def _pkcs7_unpad(ciphertext: string) -> string:
        return ciphertext[:-int(ciphertext[-1])]

    def split_password(self) -> Dict:
        """
        The 'password' field associated with a user is actually a combination of hash, salt and algorithm information
        This method splits that into its constituent fields
        :return: A dictionary containing each of the fields of the 'password' field
        """
        split_pw = self.user.password.split("$")
        return {'algorithm': split_pw[0], 'iterations': split_pw[1], 'salt': split_pw[2], 'hash': split_pw[3]}

    def encrypt(self, unencrypted_password: string) -> string:
        plaintext = self._pkcs7_pad(unencrypted_password)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(plaintext))

    def decrypt(self, b64_ciphertext: string):
        ciphertext = base64.b64decode(b64_ciphertext)
        iv = ciphertext[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._pkcs7_unpad(cipher.decrypt(ciphertext[AES.block_size:])).decode('UTF-8')




