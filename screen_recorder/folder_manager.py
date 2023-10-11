import logging
import os

logger = logging.getLogger(__name__)


class FolderManager:
    def __init__(self, folder_path: str, max_folder_size: float) -> None:
        self.folder_path = folder_path
        self.max_size = max_folder_size

    def get_all_files(self) -> list[os.DirEntry]:
        """
        :return: list of files within a record's directory, as os.PathLike objects
        """
        return list(os.scandir(self.folder_path))

    @property
    def directory_size(self) -> float:
        """
        :return: The total size of the directory, in GB.
        """
        return sum([os.path.getsize(file) for file in self.get_all_files()]) / (
            1024**3
        )

    def get_sorted_files_by_creation_time(self) -> list[os.DirEntry]:
        """
        :return: list of all the records, sorted from latest to oldest.
        """
        return sorted(
            self.get_all_files(), key=lambda x: x.stat().st_ctime, reverse=True
        )

    @property
    def max_size_exceeded(self) -> bool:
        """
        Checks whether the total size of all recordings exceeds the accepted threshold, as defined in user config (in GB).
        :return: True if the max size is exceeded, False otherwise
        """
        return self.directory_size > self.max_size

    @staticmethod
    def clear_file(filename: os.DirEntry) -> None:
        """
        :param filename: A directory entry object that will be deleted.
        :return: None
        """
        if filename.path.endswith(".avi"):
            os.remove(filename)

    def perform_cleanup(self) -> None:
        """
        This function deletes the oldest files until the overall directory size gets below the acceptable threshold.
        :return: None
        """
        files_removed = 0
        while self.max_size_exceeded:
            file_to_remove = self.get_sorted_files_by_creation_time().pop(-1)
            self.clear_file(file_to_remove)
            files_removed += 1
            logger.info(
                f"{file_to_remove} has been deleted. Current directory size: {self.directory_size} GB."
            )
        if files_removed:
            logger.info(f"{files_removed} files removed from {self.folder_path}")
