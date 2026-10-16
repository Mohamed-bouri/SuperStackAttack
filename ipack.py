#!/usr/bin/env python3
"""
ipack.py - Interactive unpack / repack tool for game image packs (res/i.p and res/default/i.p).

Format (big endian), as read by StackAttack.A(InputStream) and StackAttack.A(String,String,int):
    u16 count | count x u16 size | image 0 bytes | image 1 bytes | ...
Every image is PNG (or JPEG) and is loaded with Image.createImage().

Usage (Interactive):
    python3 ipack.py                    -> Launches the interactive menu

Usage (Command Line):
    python3 ipack.py unpack res/default/i.p art/default     -> art/default/00.png, 01.jpg, ... + list.txt
    python3 ipack.py pack   art/default res/default/i.p     -> rebuilds the pack from the files in the folder
"""

import os
import re
import struct
import sys

def kind(b):
    if b[:4] == b'\x89PNG': return 'png'
    if b[:2] == b'\xff\xd8': return 'jpg'
    if b[:3] == b'GIF': return 'gif'
    return 'bin'

def dims(b):
    if b[:4] == b'\x89PNG': return struct.unpack('>II', b[16:24])
    if b[:2] == b'\xff\xd8':
        i = 2
        while i < len(b):
            if b[i] != 0xFF: i += 1; continue
            m = b[i+1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', b[i+5:i+9]); return (w, h)
            i += 2 + struct.unpack('>H', b[i+2:i+4])[0]
    return None

def unpack(src, out):
    if not os.path.exists(src):
        raise FileNotFoundError(f"Source pack file not found: '{src}'")
    
    with open(src, 'rb') as f:
        d = f.read()
        
    n = struct.unpack('>H', d[:2])[0]
    sizes = struct.unpack('>%dH' % n, d[2:2+2*n])
    off = 2 + 2*n
    
    assert off + sum(sizes) == len(d), 'Size table does not match file length.'
    
    os.makedirs(out, exist_ok=True)
    lines = []
    
    for i, sz in enumerate(sizes):
        b = d[off:off+sz]
        off += sz
        k = kind(b)
        name = '%02d.%s' % (i, k)
        with open(os.path.join(out, name), 'wb') as f:
            f.write(b)
        wh = dims(b)
        lines.append('%02d  %-4s %6d bytes  %s' % (i, k, sz, ('%dx%d' % wh) if wh else ''))
        
    with open(os.path.join(out, 'list.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
        
    print(f'\n[SUCCESS] Unpacked {n} images to "{out}"')

def pack(folder, dst):
    if not os.path.exists(folder):
        raise FileNotFoundError(f"Source folder not found: '{folder}'")
        
    files = {}
    for f in os.listdir(folder):
        m = re.fullmatch(r'(\d+)\.(png|jpg|gif|bin)', f)
        if m: 
            files[int(m.group(1))] = f
            
    n = len(files)
    assert n and sorted(files) == list(range(n)), f'Files in "{folder}" must be numbered 00..{n-1:02d} with no gaps.'
    
    blobs = []
    for i in range(n):
        file_path = os.path.join(folder, files[i])
        with open(file_path, 'rb') as f:
            blobs.append(f.read())
            
    for i, b in enumerate(blobs):
        assert len(b) <= 32767, f'{files[i]} is {len(b)} bytes; the limit is 32767 bytes.'
        
    lst = os.path.join(folder, 'list.txt')
    if os.path.exists(lst):
        with open(lst, 'r') as f:
            for ln in f:
                m = re.match(r'(\d+)\s+\S+\s+\d+ bytes\s+(\d+)x(\d+)', ln)
                if m and int(m.group(1)) < n:
                    idx = int(m.group(1))
                    curr_dims = dims(blobs[idx])
                    orig_dims = (int(m.group(2)), int(m.group(3)))
                    if curr_dims not in (None, orig_dims):
                        print(f'WARNING: {files[idx]} is now {"x".join(map(str, curr_dims))}, was {orig_dims[0]}x{orig_dims[1]} (frames are cut at fixed sizes)')
                        
    data = struct.pack('>H', n) + struct.pack('>%dH' % n, *[len(b) for b in blobs]) + b''.join(blobs)
    
    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)
        
    with open(dst, 'wb') as f:
        f.write(data)
        
    print(f'\n[SUCCESS] Packed {n} images -> "{dst}" ({len(data)} bytes)')

def interactive_menu():
    while True:
        print("\n" + "=" * 50)
        print("         GAME IMAGE PACK TOOL (ipack.py)")
        print("=" * 50)
        print("1. Unpack an image pack (.p file -> Folder)")
        print("2. Pack a folder into an image pack (Folder -> .p file)")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            print("\n--- UNPACK MODE ---")
            src = input("Enter path to pack file (e.g., res/default/i.p): ").strip().strip('"')
            if not src:
                print("Operation cancelled.")
                continue
            
            default_out = os.path.splitext(src)[0] + "_extracted"
            out = input(f"Enter output folder path [Default: {default_out}]: ").strip().strip('"')
            if not out:
                out = default_out
            
            try:
                unpack(src, out)
            except Exception as e:
                print(f"\n[ERROR] Unpacking failed: {e}")
            
            input("\nPress Enter to return to the menu...")

        elif choice == '2':
            print("\n--- PACK MODE ---")
            folder = input("Enter path to folder containing images (e.g., art/default): ").strip().strip('"')
            if not folder:
                print("Operation cancelled.")
                continue
            
            default_dst = folder.rstrip('/\\') + ".p"
            dst = input(f"Enter destination pack file path [Default: {default_dst}]: ").strip().strip('"')
            if not dst:
                dst = default_dst
            
            try:
                pack(folder, dst)
            except Exception as e:
                print(f"\n[ERROR] Packing failed: {e}")
            
            input("\nPress Enter to return to the menu...")

        elif choice == '3':
            print("\nExiting. Goodbye!")
            break
        else:
            print("\n[!] Invalid choice. Please enter 1, 2, or 3.")

if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] in ('unpack', 'pack'):
        try:
            (unpack if sys.argv[1] == 'unpack' else pack)(sys.argv[2], sys.argv[3])
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        interactive_menu()