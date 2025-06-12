import hashlib

def get_md5(input_string):
    # Convert string to bytes if it isn't already
    if isinstance(input_string, str):
        input_bytes = input_string.encode('utf-8')
    else:
        input_bytes = input_string
    
    # Create MD5 hash
    md5_hash = hashlib.md5(input_bytes)
    
    # Return hexadecimal representation
    return md5_hash.hexdigest()