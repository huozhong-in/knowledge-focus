use notify_debouncer_full::{notify::*, new_debouncer, DebounceEventResult};
use std::path::Path;
use std::time::Duration;
use chrono;

fn main() {
    println!("启动文件监控测试程序");
    let folder = "/Users/dio/Downloads";
    println!("开始监控文件夹: {}", folder);

    // 创建去抖动器，设置去抖动延迟
    let mut debouncer = match new_debouncer(
        Duration::from_secs(2), // 去抖动时间，可根据需求调整
        None, // 使用推荐的缓存
        |res: DebounceEventResult| {
            let now = chrono::Local::now();
            match res {
                Ok(events) => {
                    for event in events {
                        println!("{}", now.format("%Y-%m-%d %H:%M:%S"));
                        println!("{:?}", event);
                    }
                },
                Err(errors) => {
                    for error in errors {
                        println!("监控错误: {:?}", error);
                    }
                }
            }
        }
    ) {
        Ok(debouncer) => debouncer,
        Err(e) => {
            println!("创建去抖动器失败: {:?}", e);
            return;
        }
    };
    
    // 开始监控指定文件夹
    if let Err(e) = debouncer.watch(Path::new(folder), RecursiveMode::Recursive) {
        println!("监控文件夹失败: {:?}", e);
        return;
    }
    
    println!("已启动监控，等待文件事件...");
    println!("请在 {} 文件夹中创建、修改或删除文件以测试", folder);
    println!("按 Ctrl+C 终止程序");
    
    // 由于 debouncer 使用的是回调函数处理事件，需要保持程序运行
    // 这里使用 std::thread::park() 保持主线程不退出
    std::thread::park();
}
