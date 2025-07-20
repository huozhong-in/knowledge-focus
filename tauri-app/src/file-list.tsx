export function FileList() {
  return (
    <div className="flex flex-col gap-2 p-4">
      <h2 className="text-lg font-semibold">文件列表</h2>
      <ul className="list-disc pl-5">
        <li>文件1.txt</li>
        <li>文件2.pdf</li>
        <li>数据集.csv</li>
        <li>报告.docx</li>
      </ul>
    </div>
  );
}