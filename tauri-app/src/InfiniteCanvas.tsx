export function InfiniteCanvas() {
    return (
        <div className="flex flex-col h-full">
        <header className="bg-gray-800 text-white p-4">
            <h1 className="text-xl font-bold">无限画布</h1>
        </header>
        <main className="flex-1 overflow-auto p-4">
            <p>这里是无限画布的内容区域。</p>
            <p>您可以在这里添加任何内容，比如文本、图片、图形等。</p>
        </main>
        </div>
    );
}