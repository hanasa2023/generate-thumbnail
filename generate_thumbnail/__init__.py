import asyncio
import io
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List

from pdf2image import convert_from_path
from PIL import Image, ImageFile
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


# 检查文件是否已经有对应的缩略图
def thumbnail_exists(file_path: Path) -> bool:
    thumbnail_path: Path = file_path.with_stem(file_path.stem + "_thumbnail")
    return thumbnail_path.exists()


# 生成图片文件的缩略图
async def generate_image_thumbnail(
    image_path: Path, thumbnail_size: tuple[float, float] = (210, 297)
) -> None:
    try:
        img: ImageFile.ImageFile = Image.open(image_path)
        img.thumbnail(thumbnail_size)
        thumbnail_path: Path = image_path.with_stem(image_path.stem + "_thumbnail")
        img.save(thumbnail_path)
        print(f"缩略图生成成功: {thumbnail_path}")
    except Exception as e:
        print(f"生成缩略图时出错: {e}")


# 生成 PDF 文件的缩略图
async def generate_pdf_thumbnail(
    pdf_path: Path, thumbnail_size: tuple[float, float] = (210, 297)
) -> None:
    try:
        print(f"正在处理 PDF 文件: {pdf_path}")
        # Convert the first page of the PDF to an image
        images: List[Image.Image] = await asyncio.to_thread(
            convert_from_path, pdf_path, first_page=1, last_page=1
        )
        if images:
            img: Image.Image = images[0]
            img.thumbnail(thumbnail_size)
            thumbnail_path = pdf_path.with_stem(
                pdf_path.stem + "_thumbnail"
            ).with_suffix(".png")
            await asyncio.to_thread(img.save, thumbnail_path)
            print(f"PDF 缩略图生成成功: {thumbnail_path}")
        else:
            print(f"无法从 PDF 文件生成图像: {pdf_path}")
    except PermissionError as e:
        print(
            f"权限错误: 无法访问文件 {pdf_path}。请检查文件是否被其他程序占用或权限不足。错误信息: {e}"
        )
    except Exception as e:
        print(f"生成 PDF 缩略图时出错: {e}")


# 生成 EPUB 文件的缩略图
async def generate_epub_thumbnail(
    epub_path: Path, thumbnail_size: tuple[float, float] = (210, 297)
):
    try:
        print(f"正在处理 EPUB 文件: {epub_path}")

        # 打开 EPUB 文件
        with zipfile.ZipFile(epub_path, "r") as epub_zip:
            # 查找 container.xml
            with epub_zip.open("META-INF/container.xml") as container_file:
                container_xml = container_file.read()
                root: ET.Element = ET.fromstring(container_xml)

                # 查找 content.opf 的位置
                rootfile: ET.Element | None = root.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                )
            if rootfile is None:
                raise ValueError("rootfile element not found in container.xml")
            opf_path = rootfile.attrib["full-path"]

            # 查找 content.opf 中的封面图片
            with epub_zip.open(opf_path) as opf_file:
                opf_xml: bytes = opf_file.read()
                opf_root: ET.Element = ET.fromstring(opf_xml)

                # 查找封面 id
                cover_id = None
                for meta in opf_root.findall(".//{http://www.idpf.org/2007/opf}meta"):
                    if meta.attrib.get("name") == "cover":
                        cover_id = meta.attrib.get("content")
                        break

                # 根据封面 id 查找封面文件路径
                if cover_id:
                    cover_href = None
                    for item in opf_root.findall(
                        ".//{http://www.idpf.org/2007/opf}item"
                    ):
                        if item.attrib.get("id") == cover_id:
                            cover_href = item.attrib.get("href")
                            break

                    # 提取封面图像
                    if cover_href:
                        cover_path = Path(opf_path).parent / cover_href
                        with epub_zip.open(str(cover_path)) as cover_file:
                            cover_data = cover_file.read()

                        # 用 PIL 生成缩略图
                        cover_image = Image.open(io.BytesIO(cover_data))
                        cover_image.thumbnail(thumbnail_size)

                        # 保存缩略图
                        thumbnail_path = epub_path.with_stem(
                            epub_path.stem + "_thumbnail"
                        ).with_suffix(".png")
                        cover_image.save(thumbnail_path)
                        print(f"EPUB 缩略图生成成功: {thumbnail_path}")
                    else:
                        print("封面文件未找到。")
                else:
                    print("未找到封面 id。")
    except Exception as e:
        print(f"生成 EPUB 缩略图时出错: {e}")


def get_thumbnail_path(file_path: Path) -> Path:
    # 缩略图与原文件在同一目录，且文件名为原文件名加上 "_thumbnail.png"
    return file_path.with_name(file_path.stem + "_thumbnail" + ".png")


# 自定义事件处理类，监控文件夹中新创建文件的事件
class NewFileHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()

    async def process_new_file(self, new_file_path: Path) -> None:
        # 检查文件是否已经生成过缩略图
        if thumbnail_exists(new_file_path):
            print(f"缩略图已存在，跳过: {new_file_path}")
            return

        # 如果是图片文件
        if new_file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif"}:
            await generate_image_thumbnail(new_file_path)

        # 如果是 PDF 文件
        elif new_file_path.suffix.lower() == ".pdf":
            await generate_pdf_thumbnail(new_file_path)

        elif new_file_path.suffix.lower() == ".epub":
            await generate_epub_thumbnail(new_file_path)

    def on_created(self, event) -> None:
        # 只处理文件
        if event.is_directory:
            return

        new_file_path: Path = Path(str(event.src_path))
        print(f"检测到新文件: {new_file_path}")

        # 忽略无关文件（如 .pyc 文件或隐藏文件）
        if (
            new_file_path.suffix.lower()
            in {
                ".pyc",
                ".log",
                ".tmp",
            }
            or new_file_path.name.startswith(".")
            or new_file_path.name.endswith("_thumbnail.png")
        ):
            print(f"跳过无关文件: {new_file_path}")
            return

        # 启动异步任务处理
        asyncio.run(self.process_new_file(new_file_path))

    def on_deleted(self, event) -> None:
        deleted_file_path: Path = Path(str(event.src_path))
        thumbnail_path: Path = get_thumbnail_path(deleted_file_path)

        if thumbnail_path.exists():
            try:
                os.remove(thumbnail_path)
                print(f"已删除缩略图: {thumbnail_path}")
            except Exception as e:
                print(f"删除缩略图时出错: {e}")


# 监控指定目录
def start_watching(directory="."):
    event_handler = NewFileHandler()
    observer = Observer()
    observer.schedule(event_handler, directory, recursive=True)
    observer.start()
    print(f"开始监控文件夹: {directory}")

    try:
        # observer.join()  # 持续监听
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("停止监控目录")
    observer.join()


if __name__ == "__main__":
    # 监控当前目录
    start_watching(".")
