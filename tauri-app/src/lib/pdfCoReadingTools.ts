/**
 * PDF共读工具 - 前端实现
 *
 * 实现与PDF应用交互的具体功能，包括：
 * - 确保辅助功能权限
 * - 用默认PDF阅读器打开PDF文件
 * - 寻找并激活PDF阅读器窗口
 * - PDF阅读器窗口截图
 */

import { 
  openPath, 
  // revealItemInDir
} from "@tauri-apps/plugin-opener"
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

interface WindowInfo {
  x: number
  y: number
  width: number
  height: number
  bounds: string
}

// PDF阅读器中心点坐标（逻辑坐标系）
interface PdfReaderCenterPoint {
  x: number
  y: number
}

/**
 * 确保辅助功能权限
 */
export async function ensureAccessibilityPermission(args: Record<string, any>): Promise<{
  success: boolean
  message?: string
}> {
  /* 确保应用有辅助功能权限，如果没有则请求权限 */
  try {
    console.log(args)
    // console.log("检查辅助功能权限...")
    let hasPermission = await checkAccessibilityPermission()
    // console.log("当前权限状态:", hasPermission)

    if (!hasPermission) {
      // console.log("权限不足，请求权限...")
      // 如果没有权限，发起请求
      const permissionGranted = await requestAccessibilityPermission()
      // console.log("权限请求结果:", permissionGranted)

      if (!permissionGranted) {
        // 用户在弹窗中选择了"拒绝"，或者没有完成授权
        // console.log("用户拒绝或未完成权限授权")
        alert(
          "未能获取辅助功能权限，无法控制其他应用。请在系统设置中手动开启。"
        )
        return { success: false, message: "用户拒绝或未完成权限授权" }
      }
      // 更新权限状态
      hasPermission = await checkAccessibilityPermission()
      // console.log("权限更新后状态:", hasPermission)
    }

    return { success: hasPermission }
  } catch (error) {
    console.error("权限检查过程中发生错误:", error)
    const errorMessage = error instanceof Error ? error.message : "未知错误"
    alert(`权限检查失败: ${errorMessage}`)
    return { success: false, message: errorMessage }
  }
}

export const handlePdfReading = async (args: Record<string, any>): Promise<PdfReaderCenterPoint | undefined> => {
  /* 用系统默认阅读器打开指定PDF，并控制阅读器窗口，实现左右平均分屏布局 */
  try {
    // 支持两种参数格式：pdfPath (前端期望) 和 pdf_path (Python函数参数)
    const { pdfPath, pdf_path } = args as { pdfPath?: string; pdf_path?: string };
    const actualPdfPath = pdfPath || pdf_path;
    
    if (!actualPdfPath) {
      console.error("PDF路径参数为空")
      return undefined;
    }
    
    // 检查辅助功能权限
    const hasPermission = await ensureAccessibilityPermission({})
    // console.log("权限检查结果:", hasPermission)

    if (hasPermission.success) {
      // --- 第1步：打开PDF并抢回焦点 ---
      const window_info = await handleActivatePdfReader({ pdfPath: actualPdfPath })
      if (window_info === undefined) {
        const result = await handleOpenPDF(actualPdfPath)
        if (!result) {
          console.error("未能打开PDF文件")
          return undefined
        }
      }
      const appWindow = Window.getCurrent()
      // const windowFactor = await getCurrentWindow().scaleFactor()
      // console.log("窗口缩放因子:", windowFactor)
      // 取得当前窗口高度
      const windowSize = await getCurrentWindow().innerSize()
      const windowHeight = windowSize.height
      // console.log("当前窗口高度:", windowHeight)

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
      // console.log("正在将本应用窗口移动到左侧...")
      await appWindow.setSize(new PhysicalSize(halfWidth, windowHeight))  // 窗口宽度变化，但高度保持不变
      // 使用 monitor.position 来处理多显示器情况更佳
      await appWindow.setPosition(
        new PhysicalPosition(monitor.position.x, monitor.position.y)
      )
      // --- 第4步：通过AppleScript将“预览”窗口置于右侧 ---
      // console.log("正在将“预览”窗口移动到右侧...")
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
      // console.log(
      //   `AppleScript将设置“预览”窗口位置为: {左上角x:${scaledHalfWidth}, 左上角y:0, 右下角x:${scaledMonitorWidth}, 右下角y:${scaledMonitorHeight}}`
      // )
      // 计算PDF阅读器的逻辑中心点坐标
      const pdf_center_point: PdfReaderCenterPoint = { x: 0, y: 0 }
      pdf_center_point.x = scaledHalfWidth + Math.floor((scaledMonitorWidth - scaledHalfWidth) / 2)
      pdf_center_point.y = Math.floor(scaledMonitorHeight / 2)
      // refer https://apple.stackexchange.com/questions/376928/apple-script-how-do-i-check-if-the-bounds-of-a-window-are-equal-to-specific-va
      
      const defaultPDFReaderName = await getPdfReaderName(actualPdfPath)
      const appleScript = `
const app = Application("${defaultPDFReaderName}");

// 确保应用至少有一个窗口，避免脚本出错
if (app.windows.length > 0) {
    const frontWindow = app.windows[0]; // 获取最前方的窗口

    // JXA 的 bounds 是一个对象: {x, y, width, height}
    // 需要将传入的坐标转换为 JXA 的格式来进行比较和设置。

    // 1. 获取窗口当前的 bounds (格式: {x, y, width, height})
    const currentBounds = frontWindow.bounds();

    // 2. 根据传入的变量，计算出目标 bounds (JXA 格式)
    const targetX = ${scaledHalfWidth};
    const targetY = 0;
    const targetWidth = ${scaledMonitorWidth} - ${scaledHalfWidth};
    const targetHeight = ${scaledMonitorHeight};

    // 3. 比较当前 bounds 和目标 bounds 的每一个属性
    //    直接比较对象 (currentBounds !== targetBounds) 是行不通的。
    if (currentBounds.x !== targetX ||
        currentBounds.y !== targetY ||
        currentBounds.width !== targetWidth ||
        currentBounds.height !== targetHeight) 
    {
        // 4. 如果不相等，就设置窗口的 bounds
        frontWindow.bounds = {
            x: targetX,
            y: targetY,
            width: targetWidth,
            height: targetHeight
        };
    }
}`
      const command = Command.create("run-applescript", [
        "-l",
        "JavaScript",
        "-e",
        appleScript,
      ])
      const output = await command.execute()
      // console.log("handleControlPdfReader() 执行结果:", output)
      // 抢回焦点
      await Window.getCurrent().setFocus()
      if (output.code !== 0) {
        console.error("handleControlPdfReader() 执行失败:", output.stderr)
      } else {
        // console.log("分屏布局设置成功！")
        return pdf_center_point
      }
    } else {
      // console.log("权限不足，打开系统设置...")
      await open(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
      )
      return undefined
    }
  } catch (error) {
    console.error("控制PDF阅读器时发生错误:", error)
    return undefined
  }
}

interface WindowStatus {
  exists: boolean
  isFrontmost: boolean
  isOccluded: boolean
  isMiniaturized: boolean
  message: string
}

export async function isPdfReaderFocused(pdfPath: string): Promise<WindowStatus> {
  /*
  判断PDF阅读器的特定窗口是否存在、是否最小化、是否是前台焦点、是否被遮挡。
  */
  const defaultPDFReaderName = await getPdfReaderName(pdfPath)
  const appleScript = `
'use strict';

/**
 * 获取并分析指定窗口的状态。
 * @param {string} appName - 目标应用程序的名称 (例如, 'Preview', 'Notes', 'Google Chrome')。
 * @param {string} windowTitle - 目标窗口的标题。支持部分匹配。
 * @returns {object} - 返回一个包含窗口状态的对象。
 */
function getWindowStatus(appName, windowTitle) {
    try {
        // 将所有与 app 对象的交互都放入 try...catch 块中 ---
        const app = Application(appName);

        // --- 1. 判断是否存在 ---
        if (!app.running()) {
            return { exists: false, isFrontmost: false, isOccluded: false, isMiniaturized: false, message: "应用 '" + appName + "' 未运行。" };
        }

        const targetWindow = app.windows().find(win => win.name().includes(windowTitle));

        if (!targetWindow) {
            return { exists: false, isFrontmost: false, isOccluded: false, isMiniaturized: false, message: "在 '" + appName + "' 中未找到标题包含 '" + windowTitle + "' 的窗口。" };
        }

        // --- 2. 判断是否最小化 ---
        const isMiniaturized = targetWindow.miniaturized();

        if (isMiniaturized) {
            return {
                exists: true,
                isFrontmost: false,
                isOccluded: false,
                isMiniaturized: true,
                message: "窗口存在，但已被最小化。"
            };
        }
        
        // --- 3. 判断是否是前台焦点窗口 ---
        const isAppFrontmost = app.frontmost();
        const isWindowFrontmostInApp = app.windows[0].name() === targetWindow.name();
        const isFrontmost = isAppFrontmost && isWindowFrontmostInApp;

        if (isFrontmost) {
            return {
                exists: true,
                isFrontmost: true,
                isOccluded: false,
                isMiniaturized: false,
                message: "窗口存在且是当前焦点窗口。"
            };
        }

        // --- 4. 推断是否被遮挡 ---
        const isOccluded = true;
        let message = "窗口存在但可能被其他应用遮挡。";
        if (isAppFrontmost && !isWindowFrontmostInApp) {
            message = "窗口存在，但可能被 "+ appName +" 的其他窗口遮挡。";
        }

        return {
            exists: true,
            isFrontmost: false,
            isOccluded: isOccluded,
            isMiniaturized: false,
            message: message
        };

    } catch (e) {
        // 如果在 try 块中的任何地方发生错误（特别是与无效应用交互时），
        // catch 块会捕获错误并返回一个友好的信息。
        return { 
            exists: false, 
            isFrontmost: false, 
            isOccluded: false,
            isMiniaturized: false,
            message: "无法与应用 '" + appName + "' 通信。它可能未安装或无权访问。错误详情: " + e.message
        };
    }
}

(function() {
    const notesStatus = getWindowStatus('${defaultPDFReaderName}', '${pdfPath.split("/").pop() || ""}');
    return JSON.stringify(notesStatus);
})();
`
  const command = Command.create("run-applescript", [
    "-l",
    "JavaScript",
    "-e",
    appleScript,
  ])
  const output = await command.execute()
  // console.log("isPdfReaderFocused() 执行结果:", output)
  if (output.code !== 0) {
    console.error("isPdfReaderFocused() 执行失败:", output.stderr)
    return { exists: false, isFrontmost: false, isOccluded: false, isMiniaturized: false, message: "执行AppleScript失败: " + output.stderr }
  }
  const result = output.stdout.trim()
  // console.log("isPdfReaderFocused() 输出:", result)
  // 解析输出的JSON字符串
  const status = JSON.parse(result)
  return status
}


export const handleActivatePdfReader = async (args: Record<string, any>): Promise<PdfReaderCenterPoint | undefined> => {
  // 激活PDF阅读器窗口
  // 支持两种参数格式：pdfPath (前端期望) 和 pdf_path (Python函数参数)
  const { pdfPath, pdf_path } = args as { pdfPath?: string; pdf_path?: string };
  const actualPdfPath = pdfPath || pdf_path;
  
  if (!actualPdfPath) {
    console.error("PDF路径参数为空")
    return undefined;
  }
  
  const pdfFileName = actualPdfPath.split("/").pop() || ""
  if (pdfFileName === "") {
    return undefined
  }
  const defaultPDFReaderName = await getPdfReaderName(actualPdfPath)
  const appleScript = `
// JXA (JavaScript for Automation) Script
//
// 功能:
// 1. 动态检测系统默认的 PDF 阅读器。
// 2. 在该应用中查找一个名字包含 "${pdfFileName}" 的窗口。
// 3. 如果窗口是最小化的，则恢复它。
// 4. 无论窗口之前状态如何，都将其激活并置于最前台。

'use strict';

// 定义主逻辑函数
function handlePdfWindow() {
    try {
        // 连接到动态确定的应用程序
        const targetApp = Application("${defaultPDFReaderName}");
        
        // 确保目标应用正在运行
        if (!targetApp.running()) {
            return "error: ${defaultPDFReaderName} is not running.";
        }

        // 查找目标窗口
        const targetWindow = targetApp.windows().find(win => {
            return win.name().includes('${pdfFileName}');
        });

        // 如果找到了符合条件的窗口
        if (targetWindow) {
            // 步骤1: 检查窗口是否是最小化的。如果是，就恢复它。
            if (targetWindow.miniaturized()) {
                targetWindow.miniaturized = false;
            }
            
            // 步骤2: 激活目标应用，使其成为当前活跃的应用
            targetApp.activate();
            
            // 步骤3: 将目标窗口置于最前台。
            targetWindow.index = 1;
            
            // 步骤4: 获取窗口的位置和尺寸信息
            const bounds = targetWindow.bounds();
            const x = bounds.x;
            const y = bounds.y;
            const width = bounds.width;
            const height = bounds.height;
            
            // 返回成功信息
            return "success|x:" + x + "|y:" + y + "|width:" + width + "|height:" + height + "|bounds:" + bounds.x + "," + bounds.y + "," + (bounds.x + bounds.width) + "," + (bounds.y + bounds.height);
        } else {
            // 如果没有找到符合条件的窗口
            return "success|no_matching_window_found";
        }

    } catch (e) {
        // 如果在执行过程中发生任何错误，捕获并返回错误信息
        return "error:" + e.message;
    }
}

// 调用函数并返回结果
handlePdfWindow();
`
  const command = Command.create("run-applescript", [
    "-l",
    "JavaScript",
    "-e",
    appleScript,
  ])
  const output = await command.execute()
  // console.log("handleActivePdfReader() 执行结果:", output)
  if (output.code !== 0) {
    console.error("handleActivePdfReader() 执行失败:", output.stderr)
    return undefined
  }

  // 解析窗口信息
  const result = output.stdout.trim()
  if (result.startsWith("success|")) {
    const parts = result.split("|")
    if (parts.length > 1 && parts[1] !== "no_matching_window_found") {
      const window_info: WindowInfo = {
        x: 0,
        y: 0,
        width: 0,
        height: 0,
        bounds: "",
      }

      // 解析各个部分
      parts.slice(1).forEach((part) => {
        if (part.startsWith("x:")) window_info.x = parseInt(part.substring(2))
        if (part.startsWith("y:")) window_info.y = parseInt(part.substring(2))
        if (part.startsWith("width:"))
          window_info.width = parseInt(part.substring(6))
        if (part.startsWith("height:"))
          window_info.height = parseInt(part.substring(7))
        if (part.startsWith("bounds:")) window_info.bounds = part.substring(7)
      })

      // console.log("pdfreader窗口信息:", window_info)
      // console.log(`窗口位置: (${window_info.x}, ${window_info.y})`)
      // console.log(`窗口大小: ${window_info.width} x ${window_info.height}`)
      // console.log(`窗口边界: ${window_info.bounds}`)

      // 计算PDF阅读器的逻辑中心点坐标
      const pdf_center_point: PdfReaderCenterPoint = { x: 0, y: 0 }
      pdf_center_point.x = window_info.x + Math.floor(window_info.width / 2)
      pdf_center_point.y = window_info.y + Math.floor(window_info.height / 2)

      return pdf_center_point
    } else {
      // console.log("PDF阅读器应用没有窗口")
      return undefined
    }
  } else {
    return undefined
  }
}

const handleOpenPDF = async (pdfPath: string): Promise<boolean> => {
  try {
    // console.log("尝试打开PDF文件:", pdfPath)
    await openPath(pdfPath)
    return true

  } catch (error) {
    console.error("打开PDF时发生错误:", error)
    return false
  }
}

export async function handlePdfReaderScreenshot(args: Record<string, any>): Promise<string> {
  // 截屏
  // 支持两种参数格式：pdfPath (前端期望) 和 pdf_path (Python函数参数)
  const { pdfPath, pdf_path } = args as { pdfPath?: string; pdf_path?: string };
  const actualPdfPath = pdfPath || pdf_path;
  
  if (!actualPdfPath) {
    console.error("PDF路径参数为空")
    return "";
  }
  const hasPermission = await checkScreenRecordingPermission()
  if (!hasPermission) {
    // 如果没有屏幕录制权限，尝试请求权限
    const permissionGranted = await requestScreenRecordingPermission()
    if (!permissionGranted) {
      // console.log(
      //   "未能获取屏幕录制权限，无法截图。请在系统设置中手动开启。"
      // )
      return ''
    }
  }
  
  // 取得actualPdfPath中文件名的部分
  const pdfFileName = actualPdfPath.split("/").pop() || ""
  if (pdfFileName === "") {
    console.error("无法获取PDF文件名，无法进行截图")
    return ''
  }
  // 激活PDF阅读器窗口，即使它被最小化了
  const window_info = await handleActivatePdfReader({ pdfPath: actualPdfPath })
  if (!window_info) {
    console.error("未能激活PDF阅读器窗口")
    return ''
  }
  const windows = await getScreenshotableWindows()
  if (windows.length === 0) {
    console.error("未找到可截图的窗口")
    return ''
  }
  let window_id = -1
  windows.forEach((win) => {
    // console.log(`APPNAME: ${win.appName}, TITLE: ${win.title}，窗口ID: ${win.id}`)
    if (win.title.includes(pdfFileName)) {
      window_id = win.id
    }
  })
  if (window_id === -1) {
    console.error(`未找到包含 "${pdfFileName}" 的窗口`)
    return ''
  }
  const path = await getWindowScreenshot(window_id)
  // console.log(path) // xx/tauri-plugin-screenshots/window-{id}.png
  // revealItemInDir(path)
  // 抢回焦点
  await Window.getCurrent().setFocus()
  return path
}

const getPdfReaderName = async (pdfPath:string): Promise<string> => {
  const appleScript = `tell application "System Events" to get name of (get default application of file "${pdfPath}")`
  const command = Command.create("run-applescript", ["-e", appleScript])
  const output = await command.execute()
  // console.log("getPdfReaderName() 执行结果:", output)
  if (output.code !== 0) {
    console.error("getPdfReaderName()执行失败:", output.stderr)
    return ""
  }
  let result = output.stdout.trim()
  // 如果是.app结束，则截取掉
  if (result.endsWith(".app")) {
    result = result.slice(0, -4)
  }
  return result
}

// 导出所有工具函数，用于注册到工具通道
export const pdfCoReadingTools = {
  ensure_accessibility_permission: ensureAccessibilityPermission,
  handle_pdf_reading: handlePdfReading,
  handle_activate_pdf_reader: handleActivatePdfReader,
  handle_pdf_reader_screenshot: handlePdfReaderScreenshot,
}
