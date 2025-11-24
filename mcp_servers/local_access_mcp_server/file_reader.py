"""
File reader with security validation.
"""

import os
from pathlib import Path

import aiofiles


class FileReader:
    """Handle secure file reading operations."""

    def __init__(self, root_folder: str):
        """
        Initialize FileReader with root folder.

        Args:
            root_folder: Absolute path to the root folder for file operations
        """
        self.root_folder = Path(root_folder).resolve()

        if not self.root_folder.exists():
            raise ValueError(f"Root folder does not exist: {self.root_folder}")

        if not self.root_folder.is_dir():
            raise ValueError(f"Root folder is not a directory: {self.root_folder}")

    def _validate_path(self, file_path: str) -> Path:
        """
        Validate that the file path is within the root folder.

        Args:
            file_path: Path to validate (relative or absolute)

        Returns:
            Resolved absolute Path object

        Raises:
            ValueError: If path is outside root folder or invalid
        """
        # Convert to Path and resolve
        if os.path.isabs(file_path):
            path = Path(file_path).resolve()
        else:
            path = (self.root_folder / file_path).resolve()

        # Check if path is within root folder
        try:
            path.relative_to(self.root_folder)
        except ValueError:
            raise ValueError(
                f"Access denied: Path '{file_path}' is outside root folder "
                f"'{self.root_folder}'"
            )

        return path

    async def read_file(self, file_path: str) -> dict:
        """
        Read file content with security validation.

        Args:
            file_path: Path to the file (relative to root or absolute within root)

        Returns:
            Dict with file info and content

        Raises:
            ValueError: If path is invalid or outside root
            FileNotFoundError: If file doesn't exist
        """
        validated_path = self._validate_path(file_path)

        if not validated_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not validated_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Read file content
        try:
            async with aiofiles.open(validated_path, "r", encoding="utf-8") as f:
                content = await f.read()
        except UnicodeDecodeError:
            # Try reading as binary if UTF-8 fails
            async with aiofiles.open(validated_path, "rb") as f:
                binary_content = await f.read()
                content = f"<Binary file, {len(binary_content)} bytes>"

        # Get file stats
        stats = validated_path.stat()

        return {
            "path": str(validated_path.relative_to(self.root_folder)),
            "absolute_path": str(validated_path),
            "name": validated_path.name,
            "size": stats.st_size,
            "extension": validated_path.suffix,
            "content": content,
        }

    async def list_files(
        self, folder_path: str = ".", extension: str = "", recursive: bool = False
    ) -> dict:
        """
        List files in a folder.

        Args:
            folder_path: Path to folder (relative to root or absolute within root)
            extension: Filter by extension (e.g., '.json'). Empty for all files.
            recursive: Whether to search subdirectories

        Returns:
            Dict with list of files

        Raises:
            ValueError: If path is invalid or outside root
        """
        validated_path = self._validate_path(folder_path)

        if not validated_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        if not validated_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")

        files = []

        if recursive:
            pattern = "**/*" if not extension else f"**/*{extension}"
            file_paths = validated_path.glob(pattern)
        else:
            pattern = "*" if not extension else f"*{extension}"
            file_paths = validated_path.glob(pattern)

        directories = []

        for file_path in file_paths:
            if file_path.is_file():
                stats = file_path.stat()
                files.append(
                    {
                        "path": str(file_path.relative_to(self.root_folder)),
                        "name": file_path.name,
                        "size": stats.st_size,
                        "extension": file_path.suffix,
                        "type": "file",
                    }
                )
            elif file_path.is_dir():
                directories.append(
                    {
                        "path": str(file_path.relative_to(self.root_folder)),
                        "name": file_path.name,
                        "type": "directory",
                    }
                )

        return {
            "folder": str(validated_path.relative_to(self.root_folder)),
            "file_count": len(files),
            "directory_count": len(directories),
            "files": files,
            "directories": directories,
        }
