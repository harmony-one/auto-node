import random
import os
import getpass
import shutil
import time
import json
import subprocess

from pyhmy import (
    cli,
    Typgpy,
    json_load
)
from .common import (
    validator_config,
    save_validator_config,
    node_config,
    save_node_config,
    saved_wallet_pass_path,
    bls_key_len,
    imported_bls_pass_file_dir,
    bls_key_dir,
    imported_wallet_pass_file_dir,
)


def _import_validator_address():
    if validator_config["validator-addr"] is None:
        print(f"{Typgpy.OKBLUE}Selecting random address in shared CLI keystore to be validator.{Typgpy.ENDC}")
        keys_list = list(cli.get_accounts_keystore().values())
        if not keys_list:
            print(f"{Typgpy.FAIL}Shared CLI keystore has no wallets{Typgpy.ENDC}")
            raise RuntimeError("Bad wallet import")
        validator_config["validator-addr"] = random.choice(keys_list)
    elif validator_config['validator-addr'] not in cli.get_accounts_keystore().values():
        print(f"{Typgpy.FAIL}Cannot create validator, {validator_config['validator-addr']} "
              f"not in shared CLI keystore.{Typgpy.ENDC}")
        raise RuntimeError("Bad wallet import")
    return validator_config["validator-addr"]


def _import_bls_passphrase():
    """
    Import BLS passphrase (from user or file).
    Returns None if using imported passphrase files.
    """
    bls_keys = [x for x in os.listdir(bls_key_dir) if not x.startswith('.') and x.endswith(".key")]
    bls_pass = [x for x in os.listdir(imported_bls_pass_file_dir) if not x.startswith('.') and x.endswith(".pass")]
    imported_bls_keys, imported_bls_pass = set(), set()
    for k in bls_keys:
        tok = k.split(".")
        if len(tok) != 2 or len(tok[0]) != bls_key_len:
            print(f"{Typgpy.FAIL}Imported BLS key file {k} has an invalid file format. "
                  f"Must be `<BLS-pub-key>.key`{Typgpy.ENDC}")
            raise RuntimeError("Bad BLS import")
        imported_bls_keys.add(tok[0])
    for p in bls_pass:
        tok = p.split(".")
        if len(tok) != 2 or len(tok[0]) != bls_key_len:
            print(f"{Typgpy.FAIL}Imported BLS passphrase file {p} has an invalid file format. "
                  f"Must be `<BLS-pub-key>.pass`{Typgpy.ENDC}")
            raise RuntimeError("Bad BLS import")
        imported_bls_pass.add(tok[0])
    if bls_pass and not bls_keys:
        print(f"{Typgpy.WARNING}BLS passphrase file(s) were imported but no BLS key files were imported. "
              f"Passphrase files are ignored.{Typgpy.ENDC}")
        return getpass.getpass(f"Enter passphrase for all {Typgpy.UNDERLINE}{len(bls_keys)} "
                               f"imported{Typgpy.ENDC} BLS keys\n> ")
    if bls_keys and bls_pass:
        print(f"{Typgpy.WARNING}Importing BLS keys with BLS passphrase files (all or nothing).{Typgpy.ENDC}")
        for k in imported_bls_keys:
            if k not in imported_bls_pass:
                print(f"{Typgpy.FAIL}Imported BLS key file for {k} "
                      f"does not have an imported passphrase file.{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import, missing BLS passphrase file.")
        return None
    if bls_keys:
        return getpass.getpass(f"Enter passphrase for all {Typgpy.UNDERLINE}{len(bls_keys)} "
                               f"imported{Typgpy.ENDC} BLS keys\n> ")
    return getpass.getpass(f"Enter passphrase for all {Typgpy.UNDERLINE}generated{Typgpy.ENDC} BLS keys\n> ")


def _import_wallet_passphrase():
    wallet_pass = [x for x in os.listdir(imported_wallet_pass_file_dir) if not x.startswith('.') and x.endswith(".pass")]
    for p in wallet_pass:
        tok = p.split('.')
        if len(tok) != 2 or not tok[0].startswith("one1"):
            print(f"{Typgpy.FAIL}Imported wallet passphrase file {p} has an invalid file format. "
                  f"Must be `<ONE-address>.pass`{Typgpy.ENDC}")
            raise RuntimeError("Bad wallet passphrase import")
        if validator_config['validator-addr'] == tok[0]:
            with open(f"{imported_wallet_pass_file_dir}/{p}", 'r', encoding='utf8') as f:
                return f.read().strip()
    return getpass.getpass(f"Enter wallet passphrase for {validator_config['validator-addr']}\n> ")


def _import_bls(passphrase):
    """
    Import BLS keys using imported passphrase files if passphrase is None.
    Otherwise, use passphrase for imported BLS key files or generated BLS keys.

    Assumes that imported BLS key files and passphrase have been validated.
    """
    bls_keys = [x for x in os.listdir(bls_key_dir) if not x.startswith('.') and x.endswith(".key")]
    bls_pass = [x for x in os.listdir(imported_bls_pass_file_dir) if not x.startswith('.') and x.endswith(".pass")]
    if passphrase is None:
        for k in bls_pass:
            shutil.copy(f"{imported_bls_pass_file_dir}/{k}", bls_key_dir)
        for k in bls_keys:  # Verify Passphrase
            try:
                cli.single_call(f"hmy keys recover-bls-key {bls_key_dir}/{k} "
                                f"--passphrase-file {imported_bls_pass_file_dir}/{k.replace('.key', '.pass')}")
            except RuntimeError as e:
                print(f"{Typgpy.FAIL}Passphrase file for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import") from e
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]

    with open("/tmp/.bls_pass", 'w', encoding='utf8') as fw:
        fw.write(passphrase)
        subprocess.call(f"chmod go-rwx /tmp/.bls_pass", shell=True, env=os.environ)
    if len(bls_keys) > 0:
        if node_config['shard'] is not None:
            print(f"{Typgpy.WARNING}[!] Shard option ignored since BLS keys were imported.{Typgpy.ENDC}")
            time.sleep(3)  # Sleep so user can read message
        for k in bls_keys:
            try:
                cli.single_call(f"hmy keys recover-bls-key {bls_key_dir}/{k} "
                                f"--passphrase-file /tmp/.bls_pass")
            except RuntimeError as e:
                print(f"{Typgpy.FAIL}Passphrase for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise RuntimeError("Bad BLS import") from e
            pass_file = f"{bls_key_dir}/{k.replace('.key', '.pass')}"
            with open(pass_file, 'w', encoding='utf8') as fw:
                fw.write(passphrase)
        os.remove("/tmp/.bls_pass")
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]
    elif node_config['shard'] is not None:
        assert isinstance(int, node_config['shard']), f"shard: {node_config['shard'] } is not an integer."
        while True:
            key = json_load(cli.single_call("hmy keys generate-bls-key --passphrase-file /tmp/.bls_pass"))
            public_bls_key = key['public-key']
            bls_file_path = key['encrypted-private-key-path']
            shard_id = json_load(cli.single_call(f"hmy --node={node_config['endpoint']} utility "
                                                 f"shard-for-bls {public_bls_key}"))["shard-id"]
            if int(shard_id) != node_config['shard']:
                os.remove(bls_file_path)
            else:
                print(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: "
                      f"{Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
                break
        shutil.copy(bls_file_path, bls_key_dir)
        pass_file = f"{bls_key_dir}/{key['public-key'].replace('0x', '')}.pass"
        with open(pass_file, 'w', encoding='utf8') as fw:
            fw.write(passphrase)
        os.remove("/tmp/.bls_pass")
        return [public_bls_key]
    else:
        key = json_load(cli.single_call("hmy keys generate-bls-key --passphrase-file /tmp/.bls_pass"))
        public_bls_key = key['public-key']
        bls_file_path = key['encrypted-private-key-path']
        shard_id = json_load(cli.single_call(f"hmy --node={node_config['endpoint']} utility "
                                             f"shard-for-bls {public_bls_key}"))["shard-id"]
        print(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: {Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
        shutil.copy(bls_file_path, bls_key_dir)
        pass_file = f"{bls_key_dir}/{key['public-key'].replace('0x', '')}.pass"
        with open(pass_file, 'w', encoding='utf8') as fw:
            fw.write(passphrase)
        os.remove("/tmp/.bls_pass")
        return [public_bls_key]


def config():
    validator_config['validator-addr'] = _import_validator_address()
    wallet_passphrase = _import_wallet_passphrase()
    bls_passphrase = _import_bls_passphrase()
    node_config['public-bls-keys'] = _import_bls(bls_passphrase)
    print("~" * 110)
    print(f"Saved Validator Information: {json.dumps(validator_config, indent=4)}")
    save_validator_config()
    print(f"Saved Node Information: {json.dumps(node_config, indent=4)}")
    save_node_config()
    with open(saved_wallet_pass_path, 'w', encoding='utf8') as f:
        f.write(wallet_passphrase)
        subprocess.call(f"chmod go-rwx {saved_wallet_pass_path}", shell=True, env=os.environ)
    print("~" * 110)
