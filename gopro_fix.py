
import os
import shutil
import datetime as dt
import pandas as pd
import re

import argparse

parser = argparse.ArgumentParser(description='GoPro Filename Fixer')

DEFAULT_ORIGIN_DRIVE = "g"
DEFAULT_ORIGIN_SUBDIR ="\\DCIM\\100GOPRO\\"
DATE_STUB = dt.datetime.today().strftime("%Y-%m-%d_%H%M")
DEFAULT_DESTINATION =f"d:\\videos\gopro_raw\{DATE_STUB}\\"

parser.add_argument("--origin_drive", default=DEFAULT_ORIGIN_DRIVE, type=str, help=f"origin drive  default ({DEFAULT_ORIGIN_DRIVE})")
parser.add_argument("--origin_subdir", default=DEFAULT_ORIGIN_SUBDIR, type=str, help=f"origin subdirectory  default ({DEFAULT_ORIGIN_SUBDIR})")
parser.add_argument("--origin_fullpath", default=None, type=str, help="fullpath for origin eg. D:\\DCIM\\100GOPRO\\")

parser.add_argument("--destination", default=DEFAULT_DESTINATION, type=str, help=f"fullpath for destingation default ({DEFAULT_DESTINATION})")
parser.add_argument("--destination_stub", default=None, type=str, help=f"stub for end of destination default")

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(f'Boolean value expected. Got {v}')


parser.add_argument("--simulate", type=str2bool, nargs='?',
                        const=True, default=False,
                        help="Simulate only,  do not rename or move files")
parser.add_argument("--move_files", type=str2bool, nargs='?',
                        const=False, default=False,
                        help="Move files from sd to destination")

args = parser.parse_args()

if args.destination != DEFAULT_DESTINATION:
    assert args.destination_stub is None, f"--destination set {args.destination} at same time as --destination_stub {args.destination_stub}"
if args.destination_stub is not None:
    args.destination = f"d:\\videos\gopro_raw\{args.destination_stub}\\"
    print(f"set destination to {args.destination}")
else:
    print("no destination_stub set?!?")

if not args.simulate:
    try:
        os.mkdir(args.destination)
        print(f"Created destination directory: {args.destination}")
    except FileExistsError:
        print(f"Destination {args.destination} already exists")
else:
    print(f"*Simulate* Not creating destination {args.destination}")

if args.origin_fullpath is None:
    TARGET = f"{args.origin_drive}:{args.origin_subdir}"
    print(f"Origin will be {TARGET}")
else:
    TARGET = args.origin_fullpath
    print(f"Origin fullpath provided: {TARGET}")

try:
    entries = os.scandir(TARGET)
except FileNotFoundError:
    print(f"Cannot find path {TARGET}")
    print("Halting.")
    exit()

print(f"Digesting {TARGET}")

FILE_MODE = 33206
DIR_MODE = 16895

files = []
for e in entries:
    ctime = dt.datetime.fromtimestamp(e.stat().st_ctime)
    files.append({'full_name': e.name, 'path': e.path, 'created': ctime, 'mode': e.stat().st_mode})

df = pd.DataFrame(files)

if len(df) == 0:
    print(f"Found {len(df)} files, halting operation")
    exit()
else:
    print(f"Found {len(df)} files")


# make sure everything is either a file or a directory.
def sanity_check(r):
    assert r['mode'] in set([FILE_MODE, DIR_MODE]), f"{r['path']} is unknown filetype {r['mode']}"
    return True

df.apply(sanity_check, axis=1)

df['dir'] = df['mode'] == DIR_MODE
df['file'] = df['mode'] == FILE_MODE

# assume everything is a file for now
assert len(
    df.loc[df['dir'] == True]) == 0, f"Unexpectedly found a directory in the DCIM folder: {df.loc[df['dir'] == True]}"


def digest_filename(r, result=None):
    fn = r['full_name']
    fr = re.compile(r"(?P<name>\w*)\.(?P<extension>\w{3})")  # a2j4l24.txt
    m = fr.search(fn)
    assert m is not None, f"filename {fn} is not in recognized format"
    return m.group(result).lower()


df['extension'] = df.apply(digest_filename, axis=1, result="extension")
df['name'] = df.apply(digest_filename, axis=1, result="name")

# make sure no unexpected extensions
known_extensions = set(['jpg', 'mp4', 'lrv', 'thm', 'wav'])
assert set(df.extension.unique()).issubset(
    known_extensions), f"unknown extension in {df.extension.unique()}. Expected only {known_extensions}"

print(f"Sanity checks passed")


# throw away unecessary files (lrv, thm)
def destroy_helpers(r):
    os.remove(r.path)
    return True


keep_extensions = set(['jpg', 'mp4'])
keep_mask = df.extension.isin(keep_extensions)

if not args.simulate:
    print(f"Throwing away any file without extension in {keep_extensions}")
    df.loc[~keep_mask].apply(destroy_helpers, axis=1)
else:
    print(f"*Simulate* Not throwing away files not in {keep_extensions}")
df = df.loc[keep_mask]

print(f"Found {len(df)} videos/photos")

# make sure we understand the filenames
chaptered_video_re = re.compile(r'G(?P<encoding>[H,X])(?P<chapter>\d{2})(?P<file_number>\d{4}).mp4', re.IGNORECASE)
looped_video_re = re.compile(r'G(?P<encoding>[H,X])(?P<loop_prefix>[a-z]{2})(?P<file_number>\d{4}).mp4', re.IGNORECASE)
photo_re = re.compile(r'GOPR(?P<file_number>\d+)\.JPG', re.IGNORECASE)


def check_filename_sanity(r):
    identified = False
    for check in [chaptered_video_re, looped_video_re, photo_re]:
        m = check.search(r.full_name)
        if m is not None:
            identified = True
    assert identified, f"I cannot parse filename {r.full_name}"
    return True


df.apply(check_filename_sanity, axis=1)

print(f"Filenames make sense")


# work out the new name
def new_name(r):
    date_str = r.created.strftime("%Y-%m-%d_%H%M")
    #path = f"{os.path.dirname(r.path)}\\"
    path = f"{args.destination}"
    m = chaptered_video_re.search(r.full_name)
    if m is not None:
        return (f"{path}{m.group('file_number')}_{m.group('chapter')}_{date_str}_gopro.mp4".lower())
    else:
        m = photo_re.search(r.full_name)
        if m is not None:
            return (f"{path}{m.group('file_number')}_{date_str}_gopro.jpg".lower())
        else:
            m = looped_video_re.search(r.full_name)
            if m is not None:
                return (f"{path}{m.group('file_number')}_{m.group('loop_prefix')}_{date_str}_gopro.mp4".lower())
            else:
                raise Exception(f"what is {r.full_name}")

print(f"Moving/renaming files (slow)")
df['new_name'] = df.apply(new_name, axis=1)

print(f"New names created")

# rename files
def renamer(r):
    try:
        print(".",end="",flush=True)
        #os.rename(r.path, r.new_name)
        #os.replace(r.path, r.new_name)  #this cannot move from one drive to another
        shutil.move(r.path, r.new_name)
    except FileNotFoundError:
        raise Exception(f"\nfailed to rename {r.path} to {r.new_name}")
    return True

if not args.simulate:
    df.apply(renamer, axis=1)
    print(f"\n{len(df)} files renamed and moved to {args.destination}")
else:
    print(f"{len(df)} files would be renamed, moved")
    print(df.columns)
    print(df.loc[:,['path', 'new_name']])

df

