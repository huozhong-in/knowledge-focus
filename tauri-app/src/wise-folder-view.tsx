import { FullDiskFolderView } from './pinned-folders';

interface FullDiskFolderPageProps {
  folderId: string;
}

// 今日文件视图
export function FullDiskFolderTodayView() {
  return <FullDiskFolderView folderId="today" />;
}

// 最近7天文件视图
export function FullDiskFolderLast7DaysView() {
  return <FullDiskFolderView folderId="last7days" />;
}

// 最近30天文件视图
export function FullDiskFolderLast30DaysView() {
  return <FullDiskFolderView folderId="last30days" />;
}

// 图片文件视图
export function FullDiskFolderImageFilesView() {
  return <FullDiskFolderView folderId="image-files" />;
}

// 音视频文件视图
export function FullDiskFolderAudioVideoFilesView() {
  return <FullDiskFolderView folderId="audio-video-files" />;
}

// 归档文件视图
export function FullDiskFolderArchiveFilesView() {
  return <FullDiskFolderView folderId="archive-files" />;
}

// 通用视图（接收folderId参数）
export function GenericWiseFolderView({ folderId }: FullDiskFolderPageProps) {
  return <FullDiskFolderView folderId={folderId} />;
}
