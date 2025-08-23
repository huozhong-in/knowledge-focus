import {
  useState,
  // useEffect,
} from "react"
import { openPath, revealItemInDir } from "@tauri-apps/plugin-opener"
import { open, Command } from "@tauri-apps/plugin-shell"
import {
  checkAccessibilityPermission,
  requestAccessibilityPermission,
  checkScreenRecordingPermission,
  requestScreenRecordingPermission,
} from "tauri-plugin-macos-permissions-api"
import {
  getCurrentWindow,
  PhysicalPosition,
  Window,
  PhysicalSize,
  availableMonitors,
  currentMonitor,
} from "@tauri-apps/api/window"
import {
  getScreenshotableWindows,
  getWindowScreenshot,
} from "tauri-plugin-screenshots-api"

interface WindowBounds {
  x: number
  y: number
  width: number
  height: number
}

interface WindowInfo {
  application_name: string
  window_name: string
  window_id: number
  bounds: WindowBounds
}

const [previewAppCenterX, setPreviewAppCenterX] = useState(0)
const [previewAppCenterY, setPreviewAppCenterY] = useState(0)
const [isReverseScroll, setIsReverseScroll] = useState(false)
const [scrollSpeed, setScrollSpeed] = useState(22)

export const handleOpenPDF = async (pdfPath: string): Promise<boolean> => {
  try {
    console.log("尝试打开PDF文件:", pdfPath)
    await openPath(pdfPath)
    // 通过Python API /windows检查PDF阅读器是否已经启动
    const pdf_file_name = pdfPath.split("/").pop() || ""
    // 重试机制：最多重试15次
    for (let attempt = 1; attempt <= 15; attempt++) {
      try {
        await new Promise((resolve) => setTimeout(resolve, 1000)) // 等待1秒钟再尝试
        const response = await fetch("http://127.0.0.1:60316/tools/windows")
        if (!response.ok) {
          throw new Error("无法获取窗口列表，可能是API未启动或网络问题")
        }
        const data = await response.json()
        const windows: WindowInfo[] = data.windows

        for (const item of windows) {
          if (item.window_name.includes(pdf_file_name)) {
            console.log(`PDF阅读器窗口已启动 (第${attempt}次尝试):`, item)
            return true
          }
        }
      } catch (error) {
        console.error(`第${attempt}次尝试获取窗口列表失败:`, error)
      }
    }
    return false
  } catch (error) {
    console.error("打开PDF时发生错误:", error)
    return false
  }
}

export const handleActivePreviewApp = async () => {
  // 激活PDF阅读器窗口
  const appleScript = `
    try
      tell application "Preview"
        -- 检查应用是否有窗口
        if (count of windows) > 0 then
          -- 取消所有最小化的窗口
          repeat with win in windows
            if miniaturized of win then
              set miniaturized of win to false
            end if
          end repeat
        end if
        -- 激活应用
        activate
        
        -- 获取前台窗口的信息
        if (count of windows) > 0 then
          set frontWin to front window
          set winBounds to bounds of frontWin
          set winX to item 1 of winBounds
          set winY to item 2 of winBounds
          set winRight to item 3 of winBounds
          set winBottom to item 4 of winBounds
          set winWidth to winRight - winX
          set winHeight to winBottom - winY
          
          -- 返回结构化信息
          return "success|x:" & winX & "|y:" & winY & "|width:" & winWidth & "|height:" & winHeight & "|bounds:" & winX & "," & winY & "," & winRight & "," & winBottom
        else
          return "success|no_windows"
        end if
      end tell
    on error errorMessage
      return "error: " & errorMessage
    end try
  `
  const command = Command.create("run-applescript", ["-e", appleScript])
  const output = await command.execute()
  if (output.code !== 0) {
    console.error("AppleScript执行失败:", output.stderr)
    return
  }

  // 解析窗口信息
  const result = output.stdout.trim()
  console.log("AppleScript 原始输出:", result)

  if (result.startsWith("success|")) {
    const parts = result.split("|")
    if (parts.length > 1 && parts[1] !== "no_windows") {
      const windowInfo = {
        x: 0,
        y: 0,
        width: 0,
        height: 0,
        bounds: "",
      }

      // 解析各个部分
      parts.slice(1).forEach((part) => {
        if (part.startsWith("x:")) windowInfo.x = parseInt(part.substring(2))
        if (part.startsWith("y:")) windowInfo.y = parseInt(part.substring(2))
        if (part.startsWith("width:"))
          windowInfo.width = parseInt(part.substring(6))
        if (part.startsWith("height:"))
          windowInfo.height = parseInt(part.substring(7))
        if (part.startsWith("bounds:")) windowInfo.bounds = part.substring(7)
      })

      console.log("Preview窗口信息:", windowInfo)
      console.log(`窗口位置: (${windowInfo.x}, ${windowInfo.y})`)
      console.log(`窗口大小: ${windowInfo.width} x ${windowInfo.height}`)
      console.log(`窗口边界: ${windowInfo.bounds}`)

      // 计算预览app的逻辑中心点坐标
      setPreviewAppCenterX(windowInfo.x + Math.floor(windowInfo.width / 2))
      setPreviewAppCenterY(windowInfo.y + Math.floor(windowInfo.height / 2))
    } else {
      console.log("Preview应用没有窗口")
    }
  } else if (result.startsWith("error:")) {
    console.error("AppleScript执行错误:", result)
  }

  // 抢回焦点
  await Window.getCurrent().setFocus()
}

export async function handlePreviewAppScreenshot(pdfPath: string) {
  // 截屏
  const hasPermission = await checkScreenRecordingPermission()
  if (!hasPermission) {
    // 如果没有屏幕录制权限，尝试请求权限
    const permissionGranted = await requestScreenRecordingPermission()
    if (!permissionGranted) {
      console.log("未能获取屏幕录制权限，无法截图。请在系统设置中手动开启。")
      return
    }
  }

  // 激活PDF阅读器窗口，即使它被最小化了
  handleActivePreviewApp()

  // 取得pdfPath中文件名的部分
  const pdfFileName = pdfPath.split("/").pop() || ""
  if (pdfFileName === "") {
    console.error("无法获取PDF文件名，无法进行截图")
    return
  }
  const windows = await getScreenshotableWindows()
  if (windows.length === 0) {
    console.error("未找到可截图的窗口")
    return
  }
  let window_id = -1
  windows.forEach((win) => {
    console.log(
      `APPNAME: ${win.appName}, TITLE: ${win.title}，窗口ID: ${win.id}`
    )
    if (win.title.includes(pdfFileName)) {
      window_id = win.id
    }
  })
  if (window_id === -1) {
    console.error(`未找到包含 "${pdfFileName}" 的窗口`)
    return
  }
  const path = await getWindowScreenshot(window_id)
  // console.log(path) // xx/tauri-plugin-screenshots/window-{id}.png
  revealItemInDir(path)
}

export async function ensureAccessibilityPermission() {
  try {
    console.log("检查辅助功能权限...")
    let hasPermission = await checkAccessibilityPermission()
    console.log("当前权限状态:", hasPermission)

    if (!hasPermission) {
      console.log("权限不足，请求权限...")
      // 如果没有权限，发起请求
      const permissionGranted = await requestAccessibilityPermission()
      console.log("权限请求结果:", permissionGranted)

      if (!permissionGranted) {
        // 用户在弹窗中选择了"拒绝"，或者没有完成授权
        console.log("用户拒绝或未完成权限授权")
        alert(
          "未能获取辅助功能权限，无法控制其他应用。请在系统设置中手动开启。"
        )
        return false
      }
      // 更新权限状态
      hasPermission = await checkAccessibilityPermission()
      console.log("权限更新后状态:", hasPermission)
    }

    return hasPermission
  } catch (error) {
    console.error("权限检查过程中发生错误:", error)
    const errorMessage = error instanceof Error ? error.message : "未知错误"
    alert(`权限检查失败: ${errorMessage}`)
    return false
  }
}

export const handleControlPreviewApp = async (pdfPath: string) => {
  try {
    console.log("开始控制预览应用...")

    // 检查辅助功能权限
    const hasPermission = await ensureAccessibilityPermission()
    console.log("权限检查结果:", hasPermission)

    if (hasPermission) {
      // --- 第1步：打开PDF并抢回焦点 ---
      const result = await handleOpenPDF(pdfPath)
      if (!result) {
        console.error("未能打开PDF文件")
        return
      }
      const appWindow = Window.getCurrent()
      const windowFactor = await getCurrentWindow().scaleFactor()
      console.log("窗口缩放因子:", windowFactor)
      await appWindow.setFocus()

      // const windowList = await Window.getAll();
      // console.log("当前所有窗口列表:", windowList);

      // --- 第2步：获取显示器信息 ---
      const monitors = await availableMonitors()
      console.log("当前可用的显示器列表:", monitors)
      const monitor = await currentMonitor()
      if (!monitor) throw new Error("无法获取主显示器信息。")
      console.log("当前显示器的缩放因子:", monitor.scaleFactor)

      const monitorSize = monitor.size
      console.log("当前显示器信息:", monitor)
      const halfWidth = monitorSize.width / 2
      console.log("当前显示器宽度的一半:", halfWidth)

      // --- 第3步：将Tauri应用窗口置于左侧 ---
      console.log("正在将本应用窗口移动到左侧...")
      await appWindow.setSize(new PhysicalSize(halfWidth, monitorSize.height))
      // 使用 monitor.position 来处理多显示器情况更佳
      await appWindow.setPosition(
        new PhysicalPosition(monitor.position.x, monitor.position.y)
      )
      // --- 第4步：通过AppleScript将“预览”窗口置于右侧 ---
      console.log("正在将“预览”窗口移动到右侧...")
      // 设置窗口的边界 {x1, y1, x2, y2}
      // x1 = 左上角x, y1 = 左上角y
      // x2 = 右下角x, y2 = 右下角y
      // AppleScript使用LogicalPosition和LogicalSize来处理窗口位置和大小，需要用scaleFactor来转换
      const scaledHalfWidth = Math.floor(halfWidth / monitor.scaleFactor)
      const scaledMonitorWidth = Math.floor(
        monitorSize.width / monitor.scaleFactor
      )
      const scaledMonitorHeight = Math.floor(
        monitorSize.height / monitor.scaleFactor
      )
      console.log(
        `AppleScript将设置“预览”窗口位置为: {左上角x:${scaledHalfWidth}, 左上角y:0, 右下角x:${scaledMonitorWidth}, 右下角y:${scaledMonitorHeight}}`
      )
      // 计算预览app的逻辑中心点坐标
      setPreviewAppCenterX(
        scaledHalfWidth + Math.floor((scaledMonitorWidth - scaledHalfWidth) / 2)
      )
      setPreviewAppCenterY(Math.floor(scaledMonitorHeight / 2))
      // refer https://apple.stackexchange.com/questions/376928/apple-script-how-do-i-check-if-the-bounds-of-a-window-are-equal-to-specific-va
      const appleScript = `
          tell application "Preview"
            if (bounds of front window) is not equal to {${scaledHalfWidth}, 0, ${scaledMonitorWidth}, ${scaledMonitorHeight}} then
              set bounds of front window to {${scaledHalfWidth}, 0, ${scaledMonitorWidth}, ${scaledMonitorHeight}}
            end if
          end tell
        `
      const command = Command.create("run-applescript", ["-e", appleScript])
      const output = await command.execute()
      if (output.code !== 0) {
        console.error("AppleScript执行失败:", output.stderr)
      } else {
        console.log("分屏布局设置成功！")
      }
    } else {
      console.log("权限不足，打开系统设置...")
      await open(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
      )
    }
  } catch (error) {
    console.error("控制预览应用时发生错误:", error)
  }
}

export const handleScrollPDF = async (direction: "up" | "down") => {
  // 控制PDF阅读器翻页
  // 向PDF阅读器的逻辑中心点的坐标发送滚动事件
  const trueScrollSpeed = isReverseScroll ? -scrollSpeed : scrollSpeed
  const response = await fetch("http://127.0.0.1:60316/tools/scroll", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      x: previewAppCenterX,
      y: previewAppCenterY,
      dy: direction === "up" ? -trueScrollSpeed : trueScrollSpeed,
    }),
  })

  if (!response.ok) {
    console.error("滚动PDF时发生错误:", response.statusText)
  }
}

export const toggleScrollDirection = () => {
  // 翻转鼠标事件中的滚动方向
  setIsReverseScroll(!isReverseScroll)
}

export const tuneScrollSpeed = (newScrollSpeed: number) => {
  // 调整鼠标事件中的滚动速度,范围在[-100~100]之间
  setScrollSpeed(Math.min(Math.max(newScrollSpeed, -100), 100))
}
