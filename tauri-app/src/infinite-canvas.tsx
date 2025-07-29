export function InfiniteCanvas() {
  return (
    <div className="flex flex-col bg-gray-100 h-full overflow-auto">
      <main className="flex-1 p-4">
        <p>这里是无限画布的内容区域。</p>
        <p>您可以在这里添加任何内容，比如文本、图片、图形等。</p>
      </main>
    </div>
  )
}
