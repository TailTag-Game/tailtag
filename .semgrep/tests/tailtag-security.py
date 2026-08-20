import ast
import django
import json
import marshal
import os
import pickle
import subprocess

import httpx
import requests
import yaml
from django.db.models.expressions import RawSQL
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from yaml import CSafeLoader, SafeLoader
from yaml import CSafeLoader as LocalCSafeLoader
from yaml import SafeLoader as LocalSafeLoader
from yaml import CSafeLoader as TailTagCSafeLoader
from yaml import SafeLoader as TailTagSafeLoader

user_input = "untrusted"

# ruleid: tailtag.python.dynamic-execution
eval(user_input)
# ruleid: tailtag.python.dynamic-execution
exec(user_input)
# ok: tailtag.python.dynamic-execution
ast.literal_eval(user_input)

# ruleid: tailtag.python.shell-execution
os.system(user_input)
# ruleid: tailtag.python.shell-execution
subprocess.run(user_input, shell=True, check=True)
# ok: tailtag.python.shell-execution
subprocess.run(["git", "status"], check=True)

# ruleid: tailtag.python.unsafe-deserialization
pickle.load(source_file)
# ruleid: tailtag.python.unsafe-deserialization
pickle.loads(user_input.encode())
# ruleid: tailtag.python.unsafe-deserialization
marshal.load(source_file)
# ruleid: tailtag.python.unsafe-deserialization
marshal.loads(user_input.encode())
# ok: tailtag.python.unsafe-deserialization
json.loads(user_input)

# ruleid: tailtag.python.unsafe-yaml-load
yaml.load(user_input)
# ok: tailtag.python.unsafe-yaml-load
yaml.safe_load(user_input)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=yaml.SafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=yaml.CSafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=SafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=CSafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=LocalSafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=LocalCSafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=TailTagSafeLoader)
# ok: tailtag.python.unsafe-yaml-load
yaml.load(user_input, Loader=TailTagCSafeLoader)


def unsafe_shadowed_loader_aliases() -> None:
    TailTagSafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=TailTagSafeLoader)
    TailTagCSafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=TailTagCSafeLoader)


def unsafe_shadowed_legacy_loader_aliases() -> None:
    SafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=SafeLoader)
    CSafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=CSafeLoader)
    LocalSafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=LocalSafeLoader)
    LocalCSafeLoader = yaml.Loader
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=LocalCSafeLoader)


def unsafe_loader_alias_parameters(
    TailTagSafeLoader: object = yaml.Loader,
    TailTagCSafeLoader: object = yaml.Loader,
) -> None:
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=TailTagSafeLoader)
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=TailTagCSafeLoader)


def unsafe_legacy_loader_alias_parameters(
    SafeLoader: object = yaml.Loader,
    CSafeLoader: object = yaml.Loader,
    LocalSafeLoader: object = yaml.Loader,
    LocalCSafeLoader: object = yaml.Loader,
) -> None:
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=SafeLoader)
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=CSafeLoader)
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=LocalSafeLoader)
    # ruleid: tailtag.python.unsafe-yaml-load
    yaml.load(user_input, Loader=LocalCSafeLoader)


# ruleid: tailtag.http.disabled-tls-verification
requests.get("https://example.test", verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.get("https://example.test", verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.Client(verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.AsyncClient(verify=False)
# ok: tailtag.http.disabled-tls-verification
requests.get("https://example.test", verify=True)

# ruleid: tailtag.django.mark-safe
mark_safe(user_input)
# ruleid: tailtag.django.mark-safe
django.utils.safestring.mark_safe(user_input)
# ok: tailtag.django.mark-safe
format_html("{}", user_input)


def render_with_local_mark_safe(mark_safe: object) -> object:
    # ok: tailtag.django.mark-safe
    return mark_safe("not Django")


# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
# ruleid: tailtag.django.dynamic-raw-sql
audit_cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
audit_cursor.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
audit_cursor.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
# ruleid: tailtag.django.dynamic-raw-sql
connection.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
connection.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
connection.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
# ruleid: tailtag.django.dynamic-raw-sql
conn.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
conn.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
conn.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
# ruleid: tailtag.django.dynamic-raw-sql
db.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
db.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
db.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))


class QueryMethods:
    def execute_queries(self) -> None:
        # ruleid: tailtag.django.dynamic-raw-sql
        self.cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
        # ruleid: tailtag.django.dynamic-raw-sql
        self.cursor.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
        # ruleid: tailtag.django.dynamic-raw-sql
        self.cursor.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
        sql = "SELECT * FROM users WHERE name = '%s'"
        # ruleid: tailtag.django.dynamic-raw-sql
        self.cursor.execute(sql % user_input)
        sql_template = "SELECT * FROM users WHERE name = '{}'"
        # ruleid: tailtag.django.dynamic-raw-sql
        self.cursor.execute(sql_template.format(user_input))
        # ruleid: tailtag.django.dynamic-raw-sql
        self.connection.cursor().execute(
            f"SELECT * FROM users WHERE name = '{user_input}'"
        )


# ruleid: tailtag.django.dynamic-raw-sql
connection.cursor().execute(f"SELECT * FROM users WHERE name = '{user_input}'")
query = f"SELECT * FROM users WHERE name = '{user_input}'"
# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute(query)
# ruleid: tailtag.django.dynamic-raw-sql
User.objects.raw(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
RawSQL(f"SELECT id FROM users WHERE name = '{user_input}'", ())
# ruleid: tailtag.django.dynamic-raw-sql
django.db.models.expressions.RawSQL(
    f"SELECT id FROM users WHERE name = '{user_input}'", ()
)
# ok: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = %s", [user_input])


class Writer:
    def execute(self, value: str) -> str:
        return value


# ok: tailtag.django.dynamic-raw-sql
Writer().execute(f"not SQL: {user_input}")
# ok: tailtag.django.dynamic-raw-sql
writer.execute(f"not SQL: {user_input}")
# ok: tailtag.django.dynamic-raw-sql
executor.execute(f"not SQL: {user_input}")
# ok: tailtag.django.dynamic-raw-sql
cursor.execute(f"SELECT * FROM users")
# ok: tailtag.django.dynamic-raw-sql
query = "SELECT * FROM users WHERE name = 'static'"
cursor.execute(query)

# ruleid: tailtag.storage.public-object-acl
s3_client.put_object(Bucket="bucket", Key="key", Body=b"x", ACL="public-read")
# ruleid: tailtag.storage.public-object-acl
s3_client.put_object(Bucket="bucket", Key="key", Body=b"x", ACL="public-read-write")
# ok: tailtag.storage.public-object-acl
s3_client.put_object(Bucket="bucket", Key="key", Body=b"x")

# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("put_object", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("upload_part", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("create_multipart_upload", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_post(Bucket="bucket", Key="key")
# ok: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("get_object", Params={})
