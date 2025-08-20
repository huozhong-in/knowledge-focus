在 macOS 上，`.bundle` 类型的“文件”确实是一种特殊的目录，它在 Finder 中被呈现为单个文件，以防止用户意外修改其内部结构。这种设计被称为“包”（Package）或“捆绑包”（Bundle）。

当您编写文件树扫描程序时，识别并跳过这些包的内部文件是至关重要的，以避免处理应用程序或插件的内部资源。

### Bundle 的特定结构特征

一个典型的 macOS 应用程序捆绑包（例如 `.app` 文件）具有明确且标准的结构。虽然其他类型的捆绑包（如 `.framework` 或 `.plugin`）结构可能略有不同，但它们通常遵循相似的约定。最常见的特征如下：

1.  **目录命名**：捆绑包本身就是一个目录，其名称以特定扩展名结尾，如 `.app`, `.bundle`, `.framework`, `.kext` 等。这个扩展名是 Finder 将其识别为包的首要依据。
2.  **`Contents` 目录**：在捆绑包的顶层，通常会有一个名为 `Contents` 的目录。这个目录是现代风格捆绑包的标志。
3.  **`Info.plist` 文件**：在 `Contents` 目录内部，必须有一个名为 `Info.plist` 的信息属性列表文件。 这是一个 XML 格式的文件，包含了关于该捆绑包的元数据，例如其标识符（`CFBundleIdentifier`）、可执行文件名（`CFBundleExecutable`）和版本号（`CFBundleVersion`）等。 缺少此文件，系统可能无法正确识别该捆绑包。
4.  **`MacOS` 目录**：`Contents` 目录中通常还包含一个 `MacOS` 目录，这里存放着捆绑包的主要可执行二进制文件。
5.  **`Resources` 目录**：用于存放应用程序图标（`.icns` 文件）、图像、声音、本地化字符串和其他资源文件。
6.  **其他目录**：可能还会有 `_CodeSignature`（用于代码签名验证）、`Frameworks`（用于嵌入的框架）和 `PlugIns`（用于插件）等目录。

总而言之，**一个以 `.app` 等特殊扩展名结尾，并且内部包含 `Contents/Info.plist` 路径的目录，几乎可以肯定是一个捆绑包**。

### 在 Rust 中判断并跳过其内部文件

在 Rust 中扫描文件树时，最常用的库是 `walkdir`。这个库提供了在遍历过程中跳过特定目录内容的功能，非常适合处理 macOS 的捆绑包。

以下是几种在 Rust 中识别捆绑包的方法，按可靠性递增排序：

#### 方法 1：检查文件扩展名（简单快捷）

这是最简单的方法。您可以维护一个已知捆绑包扩展名的列表，并在遍历时检查目录的名称。

#### 方法 2：检查内部结构（更可靠）

为了更准确地识别，您可以在检测到具有可疑扩展名的目录后，进一步检查其内部是否存在 `Contents/Info.plist` 文件。这种方法可以有效避免错误地将普通目录（例如，用户创建的名为 `data.bundle` 的文件夹）识别为捆绑包。

#### 方法 3：检查文件系统元数据（最可靠，但更复杂）

macOS 的文件系统为作为“包”的目录设置了特定的元数据属性。可以通过 `mdls -name kMDItemContentType /path/to/bundle` 命令查看，如果输出包含 `com.apple.package`，则它是一个包。 在 Rust 中直接访问此 macOS 特有的元数据比较复杂，可能需要调用原生 API（通过 `Core Foundation` 框架）或执行子进程来调用 `mdls` 命令。对于大多数文件扫描场景，结合方法1和2已经足够健壮。

### Rust 代码示例

下面的示例使用了 `walkdir` 库，并结合了**扩展名检查**和**内部结构检查**来识别和跳过捆绑包。

首先，将 `walkdir` 添加到您的 `Cargo.toml` 文件中：

```toml
[dependencies]
walkdir = "2"
```

然后，在您的 Rust 代码中使用以下逻辑：

```rust
use std::collections::HashSet;
use std::path::Path;
use walkdir::WalkDir;

/// 检查给定的目录路径是否像一个 macOS 捆绑包。
///
/// 方法：
/// 1. 检查目录是否以常见的捆绑包扩展名结尾。
/// 2. 如果是，则进一步检查其内部是否包含 "Contents/Info.plist" 文件。
fn is_macos_bundle(path: &Path) -> bool {
    // 确保我们正在检查的是一个目录
    if !path.is_dir() {
        return false;
    }

    // 常见的 macOS 捆绑包/包扩展名列表
    let bundle_extensions: HashSet<&str> = [
        "app", "bundle", "framework", "plugin", "kext", "docset",
        "qlgenerator", "mdimporter", "saver", "component", "xpc",
    ]
    .iter()
    .cloned()
    .collect();

    if let Some(extension) = path.extension().and_then(|s| s.to_str()) {
        if bundle_extensions.contains(extension) {
            // 为增加可靠性，检查是否存在 Info.plist 文件
            let info_plist_path = path.join("Contents").join("Info.plist");
            if info_plist_path.exists() {
                return true;
            }
        }
    }

    false
}

fn main() {
    // 替换为您想要扫描的起始路径
    let start_path = "."; 

    // WalkDir::new 创建一个迭代器
    let mut walker = WalkDir::new(start_path).into_iter();

    println!("开始扫描目录: {}", start_path);

    loop {
        // 使用 loop 和 next() 手动控制迭代过程
        let entry = match walker.next() {
            Some(Ok(entry)) => entry,
            Some(Err(e)) => {
                eprintln!("错误: {}", e);
                continue; // 发生错误时跳过
            }
            None => break, // 迭代结束
        };

        let path = entry.path();

        // 检查当前条目是否是一个 macOS 捆绑包
        if is_macos_bundle(path) {
            println!("发现并跳过捆绑包: {}", path.display());
            // 这是关键：告诉迭代器不要进入当前这个目录
            walker.skip_current_dir(); 
        } else {
            // 处理非捆绑包的文件或目录
            println!("{}", path.display());
        }
    }

    println!("扫描完成。");
}
```

#### 代码解释：

1.  **`is_macos_bundle` 函数**：
    *   它首先检查路径是否确实是一个目录。
    *   然后，它会检查目录的扩展名是否在预定义的 `bundle_extensions` 集合中。
    *   如果扩展名匹配，它会执行一个更严格的检查：确认 `Contents/Info.plist` 文件是否存在于该目录内，这大大提高了准确性。

2.  **`main` 函数中的遍历逻辑**：
    *   我们使用 `WalkDir::new(start_path).into_iter()` 创建一个目录遍历器。
    *   关键在于使用 `loop` 和 `walker.next()` 来手动推进迭代，而不是简单的 `for` 循环。这给了我们在循环体内控制迭代器行为的能力。
    *   对于每个文件系统条目，我们调用 `is_macos_bundle` 函数进行判断。
    *   如果函数返回 `true`，我们打印一条消息，并调用 **`walker.skip_current_dir()`**。这个方法会阻止 `walkdir` 迭代器进入当前目录的任何子文件和子目录，从而完美地实现了“跳过其内部文件”的需求。
    *   如果不是捆绑包，就正常处理（这里只是打印路径）。