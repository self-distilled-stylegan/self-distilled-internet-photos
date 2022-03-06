# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Use this script to download and parse the SDIP dataset. See description in README.md.

For SD-Flickr Domains (SD-Dogs, SD-Elephants):
Run the [download.py](download.py) script, e.g.:
python download.py --dataset dog

For SD-LSUN Domains (SD-Bicycles, SD-Horses):
1. Download the data from http://dl.yf.io/lsun/objects/. Then, unzip it and extract the images as presented in https://github.com/fyu/lsun. For example:
python lsun/data.py export bicycle/ --out_dir ./bicycles/

2. Process the images using the [download.py](download.py) script, e.g.:
python download.py --lsun_data ../lsun/bicycles/ --dataset bicycle
"""

import json
import argparse
import os
import sys
from PIL import Image
import PIL
import numpy
from tqdm import tqdm
import requests
from io import BytesIO
import threading


def thread(json_split, thread_id, progress, lock, failed_urls_lock, split_size, is_lsun, rescale_size, args, failed_urls):
    start_idx = split_size * thread_id
    for idx, line in enumerate(json_split):
        if lock is not None:
            lock.acquire()
            try:
                progress.update()
            finally:
                lock.release()
        else:
            progress.update()
        out_path = os.path.join(args.out_dir, "%0d.%s" % (idx + start_idx, args.extension ))
        if os.path.isfile(out_path):
            continue
        image_name = line['image_name']
        bbox = line['bounding_box']
        if is_lsun:
            image_path = args.lsun_data
            for i in range(6):
                image_path = os.path.join(image_path, image_name[i])
            image_path = os.path.join(image_path, image_name)
            img = Image.open(image_path)
        else:
            try:
                response = requests.get(image_name)
                img = Image.open(BytesIO(response.content))
            except PIL.UnidentifiedImageError:
                if failed_urls_lock is not None:
                    failed_urls_lock.acquire()
                    try:
                        failed_urls.append(image_name)
                    finally:
                        failed_urls_lock.release()
                else:
                    failed_urls.append(image_name)
                continue
        if len(img.split()) == 4:
            img = img.convert('RGB')
        img = numpy.asarray(img)
        img = img[bbox[0]:bbox[1], bbox[2]:bbox[3]]
        img = Image.fromarray(numpy.uint8(img))
        img = img.resize((rescale_size, rescale_size), Image.LANCZOS)
        try:
            img.save(out_path)
        except:
            print(out_path)
            img.save(out_path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lsun_data', default='', help='Path to the LSUN parsed dataset')
    parser.add_argument('--json', default='', help='path to the dataset json file')
    parser.add_argument('--out_dir', default='', help='Output directory, default is SDIP_{dataset}')
    parser.add_argument('--dataset', default='horse', choices=['horse', 'bicycle', 'elephant', 'dog'], help='Which Dataset configuration to use')
    parser.add_argument('--extension', default='jpg', choices=['png', 'jpg'], help='image format')
    parser.add_argument('--num_threads', type=int, default=16
                        ,  help='number of threads')
    args = parser.parse_args()

    lsun_mapping = {'horse': True,
                    'bicycle': True,
                    'elephant': False,
                    'dog': False}
    sizes = {'horse': 256,
             'elephant': 512,
             'dog': 1024,
             'bicycle': 256}
    json_names = {'horse': 'horses.json',
                  'elephant': 'elephants.json',
                  'dog': 'dogs.json',
                  'bicycle': 'bicycle.json'}

    if args.json == '':
        args.json = json_names[args.dataset]
    if args.out_dir == '':
        args.out_dir = "SDIP_%s" % args.dataset
    rescale_size = sizes[args.dataset]
    is_lsun = lsun_mapping[args.dataset]

    with open(args.json) as f:
        json_content = json.load(f)

    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)

    if is_lsun:
        assert args.lsun_data != '', "Please download and parse LSUN %s: https://github.com/fyu/lsun, then pass the directory using --lsun_data" % args.dataset
    failed_urls = []

    num_threads = args.num_threads
    progress = tqdm(total=len(json_content))
    if num_threads == 1:
        thread(json_content, 0, progress, None, None, 0, is_lsun, rescale_size, args, failed_urls)
    else:
        groups = []
        threads = []
        lock = threading.Lock()
        failed_urls_lock = threading.Lock()
        split_size = len(json_content) // num_threads
        for i in range(num_threads):
            if i < num_threads - 1:
                groups.append(json_content[i * split_size: (i + 1) * split_size])
            else:
                groups.append(json_content[i * split_size:])
        for i in range(num_threads):
            threads.append(
                threading.Thread(target=thread, args=(groups[i], i, progress, lock, failed_urls_lock, split_size, is_lsun, rescale_size, args, failed_urls)))
        for i in range(num_threads):
            threads[i].start()
        for i in range(num_threads):
            threads[i].join()
    progress.close()

    print("Done. Images were saved to %s" % args.out_dir)
    if not is_lsun:
        print("Failed URLs:")
        for url in failed_urls:
            print(url)

if __name__ == '__main__':
    main()
