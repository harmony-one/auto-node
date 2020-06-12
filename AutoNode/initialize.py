import os
import getpass
import shutil
import time
import json
import subprocess

from pyhmy import (
    cli,
    exceptions,
    json_load,
    Typgpy,
    validator,
    staking
)

from .common import (
    log,
    validator_config,
    save_validator_config,
    node_config,
    save_node_config,
    b32_addr_len,
    bls_key_len,
    bls_key_dir,
    imported_wallet_pass_file_dir,
    cli_bin_path,
    protect_file,
    save_protected_file,
    user,
    harmony_dir,
    node_dir,
    node_sh_log_dir
)
from .util import (
    input_with_print
)
from .passphrase import (
    encrypt_wallet_passphrase,
    is_valid_passphrase
)


def _import_validator_address():
    if validator_config["validator-addr"] is None:
        _input_validator_address()
    if validator_config['validator-addr'] not in cli.get_accounts_keystore().values():
        log(f"{Typgpy.FAIL}Cannot create validator, {validator_config['validator-addr']} "
            f"not in shared CLI keystore.{Typgpy.ENDC}")
        raise SystemExit("Bad wallet import or validator config.")


def _input_validator_address():
    keys_list = list(sorted(cli.get_accounts_keystore().values()))
    if not keys_list:
        log(f"{Typgpy.FAIL}CLI keystore has no wallets.{Typgpy.ENDC}")
        raise SystemExit("Bad wallet import.")
    log(f"{Typgpy.HEADER}Keystore Wallet Addresses:{Typgpy.ENDC}")
    for i, addr in enumerate(keys_list):
        log(f"{Typgpy.BOLD}{Typgpy.OKBLUE}#{i}{Typgpy.ENDC}\t{Typgpy.OKGREEN}{addr}{Typgpy.ENDC}")
    log("")
    index = None
    while True:
        try:
            index = input_with_print(f"{Typgpy.HEADER}Which wallet would you like to use? {Typgpy.ENDC}\n"
                                     f"> {Typgpy.OKBLUE}#").strip()
            validator_config["validator-addr"] = keys_list[int(index)]
            log(f"{Typgpy.HEADER}Using validator {Typgpy.OKGREEN}{keys_list[int(index)]}{Typgpy.ENDC}")
            break
        except (IndexError, TypeError, ValueError) as e:
            log(f"{Typgpy.FAIL}Input `{index}` is not valid, error: {e}{Typgpy.ENDC}")


def _input_validator_field(field_name, set_func):
    existing = validator_config[field_name]
    prompt = (f"{Typgpy.HEADER}Enter {field_name}: {'' if not existing else f'({existing})'}{Typgpy.ENDC}\n"
              f"> {Typgpy.OKBLUE}")
    while True:
        raw_input = None
        try:
            raw_input = input_with_print(prompt.strip())
            if raw_input == '':
                set_func(existing)
                break
            else:
                set_func(raw_input)
                break
        except exceptions.InvalidValidatorError as e:
            if raw_input is not None:
                log(f"{Typgpy.FAIL}Input `{raw_input}` is not valid, error: {e}{Typgpy.ENDC}")


def _display_warning(field_name):
    log(f'{Typgpy.WARNING}{field_name} can not be changed after creation!{Typgpy.ENDC}')


def _bls_filter(file_name, suffix):
    if file_name.startswith('.') or not file_name.endswith(suffix):
        return False
    tok = file_name.split(".")
    if len(tok) != 2 or len(tok[0]) != bls_key_len:
        return False
    return True


def _wallet_pass_filter(file_name):
    if not file_name.startswith('one1') or not file_name.endswith(".pass"):
        return False
    tok = file_name.split(".")
    if len(tok) != 2 or len(tok[0]) != b32_addr_len:
        return False
    return True


def _save_protected_file(file_content, file_path, verbose=True):
    try:
        save_protected_file(file_content, file_path, verbose=verbose)
    except Exception as e:
        raise SystemExit(e)


def _import_bls_passphrase():
    """
    Import BLS passphrase (from user or file).
    Returns None if using imported passphrase files.
    """
    bls_keys = list(filter(lambda e: _bls_filter(e, '.key'), os.listdir(bls_key_dir)))
    bls_pass = list(filter(lambda e: _bls_filter(e, '.pass'), os.listdir(bls_key_dir)))
    imported_bls_keys, imported_bls_pass = set(), set()
    for k in bls_keys:
        imported_bls_keys.add(k.split('.')[0])
    for p in bls_pass:
        imported_bls_pass.add(p.split('.')[0])
    if bls_pass and not bls_keys:
        log(f"{Typgpy.WARNING}BLS passphrase file(s) were imported but no BLS key files were imported. "
            f"Passphrase files are ignored.{Typgpy.ENDC}")
        return getpass.getpass(f"Enter passphrase for {Typgpy.UNDERLINE}generated{Typgpy.ENDC} BLS key\n> ")
    if bls_keys and bls_pass:
        log(f"{Typgpy.WARNING}Importing BLS keys with BLS passphrase files (all or nothing).{Typgpy.ENDC}")
        for k in imported_bls_keys:
            if k not in imported_bls_pass:
                log(f"{Typgpy.FAIL}Imported BLS key file for {k} "
                    f"does not have an imported passphrase file.{Typgpy.ENDC}")
                raise SystemExit("Bad BLS import, missing BLS passphrase file.")
        return None
    if bls_keys:
        return getpass.getpass(f"Enter passphrase for all {Typgpy.UNDERLINE}{len(bls_keys)} "
                               f"imported{Typgpy.ENDC} BLS keys\n> ")
    return getpass.getpass(f"Enter passphrase for {Typgpy.UNDERLINE}generated{Typgpy.ENDC} BLS key\n> ")


def _import_bls(passphrase):
    """
    Import BLS keys using imported passphrase files if passphrase is None.
    Otherwise, use passphrase for imported BLS key files or generated BLS keys.

    Assumes that imported BLS key files and passphrase have been validated.
    """
    bls_keys = list(filter(lambda e: _bls_filter(e, '.key'), os.listdir(bls_key_dir)))
    if passphrase is None:  # Assumes passphrase files were imported when passphrase is None.
        if node_config['shard'] is not None:
            log(f"{Typgpy.WARNING}[!] Shard option ignored since BLS keys were imported.{Typgpy.ENDC}")
            time.sleep(3)  # Sleep so user can read message
        for k in bls_keys:
            passphrase_file = f"{bls_key_dir}/{k.replace('.key', '.pass')}"
            if protect_file(passphrase_file) != 0:
                raise SystemExit(f"Unable to protect `{passphrase_file}`, check user ({user}) "
                                 f"permissions on file.")
            try:
                cli.single_call(['hmy', 'keys', 'recover-bls-key', f'{bls_key_dir}/{k}',
                                 '--passphrase-file', passphrase_file])
            except RuntimeError as e:
                log(f"{Typgpy.FAIL}Passphrase file for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise SystemExit("Bad BLS import")
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]

    tmp_bls_pass_path = f"{os.environ['HOME']}/.bls_pass"
    _save_protected_file(passphrase, tmp_bls_pass_path, verbose=False)
    if len(bls_keys):
        if node_config['shard'] is not None:
            log(f"{Typgpy.WARNING}[!] Shard option ignored since BLS keys were imported.{Typgpy.ENDC}")
            time.sleep(3)  # Sleep so user can read message
        for k in bls_keys:
            try:
                cli.single_call(['hmy', 'keys', 'recover-bls-key', f'{bls_key_dir}/{k}',
                                 '--passphrase-file', tmp_bls_pass_path])
            except RuntimeError as e:
                log(f"{Typgpy.FAIL}Passphrase for {k} is not correct. Error: {e}{Typgpy.ENDC}")
                raise SystemExit("Bad BLS import")
            _save_protected_file(passphrase, f"{bls_key_dir}/{k.replace('.key', '.pass')}")
        os.remove(tmp_bls_pass_path)
        return [k.replace('.key', '').replace('0x', '') for k in bls_keys]
    elif node_config['shard'] is not None:
        assert isinstance(node_config['shard'], int), f"shard: {node_config['shard']} is not an integer."
        while True:
            key = json_load(cli.single_call(['hmy', 'keys', 'generate-bls-key', '--passphrase-file', tmp_bls_pass_path]))
            public_bls_key, bls_file_path = key['public-key'], key['encrypted-private-key-path']
            shard_id = json_load(cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'utility',
                                                  'shard-for-bls', public_bls_key]))['shard-id']
            if int(shard_id) != node_config['shard']:
                os.remove(bls_file_path)
            else:
                log(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: "
                    f"{Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
                break
        shutil.move(bls_file_path, bls_key_dir)
        _save_protected_file(passphrase, f"{bls_key_dir}/{key['public-key'].replace('0x', '')}.pass")
        os.remove(tmp_bls_pass_path)
        return [public_bls_key]
    else:
        key = json_load(cli.single_call(['hmy', 'keys', 'generate-bls-key', '--passphrase-file', tmp_bls_pass_path]))
        public_bls_key = key['public-key']
        bls_file_path = key['encrypted-private-key-path']
        shard_id = json_load(cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'utility',
                                              'shard-for-bls', public_bls_key]))['shard-id']
        log(f"{Typgpy.OKGREEN}Generated BLS key for shard {shard_id}: {Typgpy.OKBLUE}{public_bls_key}{Typgpy.ENDC}")
        shutil.move(bls_file_path, bls_key_dir)
        _save_protected_file(passphrase, f"{bls_key_dir}/{key['public-key'].replace('0x', '')}.pass")
        os.remove(tmp_bls_pass_path)
        return [public_bls_key]


def _assert_same_shard_bls_keys(public_keys):
    ref_shard = None
    for key in public_keys:
        shard = json_load(cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'utility',
                                           'shard-for-bls', key]))['shard-id']
        if ref_shard is None:
            ref_shard = shard
        assert shard == ref_shard, f"Bls keys {public_keys} are not for same shard, {shard} != {ref_shard}"


def make_directories():
    os.makedirs(harmony_dir, exist_ok=True)
    os.makedirs(node_dir, exist_ok=True)
    os.makedirs(node_sh_log_dir, exist_ok=True)
    os.makedirs(bls_key_dir, exist_ok=True)
    os.makedirs(imported_wallet_pass_file_dir, exist_ok=True)


def update_cli():
    cli.download(cli_bin_path, replace=True)


def setup_node_config():
    """
    Setup configs needed to run a node.
    """
    make_directories()
    bls_passphrase = _import_bls_passphrase()
    public_bls_keys = _import_bls(bls_passphrase)
    _assert_same_shard_bls_keys(public_bls_keys)
    node_config['public-bls-keys'] = public_bls_keys
    save_node_config()


def setup_validator_config():
    """
    Setup configs needed to handle a validator.
    """
    if node_config['no-validator']:
        log(f"{Typgpy.WARNING}Node config specify no validator automation, skipping setup...{Typgpy.ENDC}")
        return
    assert node_config['public-bls-keys'], f"sanity check: node config is not setup."

    make_directories()
    interactive_setup_validator()
    shard_id = json_load(cli.single_call(['hmy', '--node', f'{node_config["endpoint"]}', 'utility',
                                          'shard-for-bls', node_config['public-bls-keys'][0]]))['shard-id']
    log("~" * 110)
    log(f"Shard ID: {shard_id}")
    log(f"Saved Validator Information: {json.dumps(validator_config, indent=4)}")
    save_validator_config()
    log("~" * 110)


def setup_wallet_passphrase():
    """
    Setup wallet passphrase (encrypted).
    """
    if node_config['no-validator']:
        log(f"{Typgpy.WARNING}Node config specify no validator automation, skipping wallet setup...{Typgpy.ENDC}")
        return
    passphrase = get_wallet_passphrase()
    save_wallet_passphrase(passphrase)


def interactive_setup_validator():
    """
    Interactively take validator information, always ask for all fields
    """
    if not validator_config['validator-addr']:
        _input_validator_address()

    v = validator.Validator(validator_config['validator-addr'])
    if validator_config['validator-addr'] in staking.get_all_validator_addresses(node_config['endpoint']):
        v.load_from_blockchain(node_config['endpoint'])
        # Can immediately load validator config since information is from on-chain data.
        for key, value in v.export().items():
            assert value is not None, f"sanity check: validated config ({key}) should not be None"
            validator_config[key] = str(value)

    update_validator = True
    if all(el is not None for el in validator_config.values()):
        log(f"{Typgpy.HEADER}Validator Config:{Typgpy.OKGREEN}{json.dumps(validator_config, indent=2)}{Typgpy.ENDC}")
        if input_with_print("Update validator? [Y]/n\n> ").lower() not in {'y', 'yes'}:
            try:
                v.load(validator_config)  # The act of loading will check params
                update_validator = False
            except exceptions.InvalidValidatorError as e:
                log(f"{Typgpy.FAIL}Failed to load validator information, error {e}{Typgpy.ENDC}")
                log(f"{Typgpy.WARNING}Re-enter validator info:{Typgpy.ENDC}")
                update_validator = True

    if update_validator:
        _input_validator_field('name', v.set_name)
        _input_validator_field('website', v.set_website)
        _input_validator_field('security-contact', v.set_security_contact)
        _input_validator_field('identity', v.set_identity)
        _input_validator_field('details', v.set_details)
        _input_validator_field('min-self-delegation', v.set_min_self_delegation)
        _input_validator_field('max-total-delegation', v.set_max_total_delegation)
        _input_validator_field('amount', v.set_amount)
        _display_warning('max-rate')
        _input_validator_field('max-rate', v.set_max_rate)
        _display_warning('max-change-rate')
        _input_validator_field('max-change-rate', v.set_max_change_rate)
        _input_validator_field('rate', v.set_rate)
        for key, value in v.export().items():
            assert value is not None, f"sanity check: validated config ({key}) should not be None"
            validator_config[key] = str(value)


def get_wallet_passphrase():
    """
    Get wallet passphrase from wallet passphrase directory, if present.
    Otherwise get it interactively from user.
    """
    wallet_pass = filter(_wallet_pass_filter, os.listdir(imported_wallet_pass_file_dir))
    for p in wallet_pass:
        if validator_config['validator-addr'] == p.split('.')[0]:
            passphrase_file = f"{imported_wallet_pass_file_dir}/{p}"
            try:
                with open(passphrase_file, 'r', encoding='utf8') as f:
                    return f.read().strip()
            except (IOError, PermissionError) as e:
                raise AssertionError(f"Failed to import passphrase from {passphrase_file}, error: {e}")
    return getpass.getpass(f"Enter wallet passphrase for {validator_config['validator-addr']}\n> ")


def save_wallet_passphrase(passphrase):
    """
    Encrypt and save wallet passphrase in node config.
    """
    is_node_running = subprocess.call("pgrep harmony", shell=True, env=os.environ) == 0
    assert is_node_running, "Harmony process is not running, cannot save wallet passphrase"
    addr = validator_config["validator-addr"]
    assert addr, "Validator was not setup, cannot save passphrase"
    assert is_valid_passphrase(passphrase, addr), f"Invalid passphrase for {addr}"
    log(f"{Typgpy.HEADER}Encrypting and saving wallet passphrase.{Typgpy.ENDC}")
    node_config["encrypted-wallet-passphrase"] = encrypt_wallet_passphrase(passphrase)
    save_node_config()
