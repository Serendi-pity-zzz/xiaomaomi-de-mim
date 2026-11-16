"""组长集成基线；成员模块通过 service.py 接入。"""
import hashlib
import hmac
import random
import struct
from PIL import Image, ImageDraw
import qrcode

def generate(public):
    if not public or len(public.encode()) > 1200:
        raise ValueError('公开信息应为 1–1200 字节')
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
    qr.add_data(public)
    qr.make(fit=True)
    code = qr.make_image().convert('RGB')
    # 猫咪区域放在二维码右侧，保留全部功能图案及静区。
    out = Image.new('RGB', (code.width + 200, max(code.height, 256)), 'white')
    out.paste(code, (0, 0))
    d = ImageDraw.Draw(out)
    x = code.width
    d.polygon([(x+20,170),(x+25,35),(x+80,75),(x+130,75),(x+175,35),(x+180,170)], fill='#b1b8d7')
    d.ellipse((x+20,65,x+180,225), fill='#b1b8d7')
    for a in (65,135):
        d.ellipse((x+a-5,125,x+a+5,140), fill='#25335a')
    d.polygon([(x+94,153),(x+106,153),(x+100,162)], fill='#a03b6d')
    return out

def positions(im, key):
    if im.width < 200 or im.height < 240:
        raise ValueError('图像尺寸不符合载体协议')
    p = [(x,y,c) for y in range(32,232) for x in range(im.width-180,im.width-20) for c in range(3)]
    if key:
        random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(),'big')).shuffle(p)
    return p

def embed(im, secret, key=''):
    im = im.convert('RGB').copy()
    data = secret.encode('utf-8')
    packet = b'CAT1' + struct.pack('>I',len(data)) + hmac.new(key.encode(),data,'sha256').digest() + data
    p = positions(im,key)
    if len(packet)*8 > len(p):
        raise ValueError('秘密信息超过容量（最多 11960 字节）')
    for i in range(len(packet)*8):
        x,y,c = p[i]
        rgb = list(im.getpixel((x,y)))
        rgb[c] = (rgb[c]&254) | ((packet[i//8] >> (7-i%8))&1)
        im.putpixel((x,y),tuple(rgb))
    return im

def extract(im,key=''):
    im=im.convert('RGB')
    p=positions(im,key)
    def read(n):
        return bytes(sum((im.getpixel(p[i+j][0:2])[p[i+j][2]]&1) << (7-j) for j in range(8)) for i in range(0,n*8,8))
    head=read(40)
    if head[:4]!=b'CAT1':
        return {'status':'unknown','secret':None,'detail':'无有效标记：密钥错误、载体损坏或未嵌入'}
    n=struct.unpack('>I',head[4:8])[0]
    if n > len(p)//8-40:
        return {'status':'failed','secret':None,'detail':'长度字段损坏'}
    data=read(40+n)[40:]
    if not hmac.compare_digest(head[8:40],hmac.new(key.encode(),data,'sha256').digest()):
        return {'status':'failed','secret':None,'detail':'消息校验失败'}
    try:
        secret=data.decode('utf-8')
    except UnicodeDecodeError:
        return {'status':'failed','secret':None,'detail':'文本编码无效'}
    return {'status':'passed','secret':secret,'detail':'消息完整；不代表整幅图像完整'}
