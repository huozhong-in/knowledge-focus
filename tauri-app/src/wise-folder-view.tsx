import { WiseFolderView } from './pinned-folders';

interface WiseFolderPageProps {
  folderId: string;
}

// 今日文件视图
export function WiseFolderTodayView() {
  return <WiseFolderView folderId="today" />;
}

// 最近7天文件视图
export function WiseFolderLast7DaysView() {
  return <WiseFolderView folderId="last7days" />;
}

// 最近30天文件视图
export function WiseFolderLast30DaysView() {
  return <WiseFolderView folderId="last30days" />;
}

// 图片文件视图
export function WiseFolderImageFilesView() {
  return <WiseFolderView folderId="image-files" />;
}

// 音视频文件视图
export function WiseFolderAudioVideoFilesView() {
  return <WiseFolderView folderId="audio-video-files" />;
}

// 归档文件视图
export function WiseFolderArchiveFilesView() {
  return <WiseFolderView folderId="archive-files" />;
}

// 通用视图（接收folderId参数）
export function GenericWiseFolderView({ folderId }: WiseFolderPageProps) {
  return <WiseFolderView folderId={folderId} />;
}
