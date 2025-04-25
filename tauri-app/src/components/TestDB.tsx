import { useEffect, useState } from 'react';
import { loadDB } from '../lib/utils';

export function TestDB() {
    const [testResult, setTestResult] = useState<string>('未测试');

    useEffect(() => {
        const testDB = async () => {
            try {
                const db = await loadDB();
                setTestResult('数据库连接成功！路径: ' + db.path);
                
                // 测试插入数据，随机生成
                const randomId = Math.floor(Math.random() * 1000000);
                const randomValue = 'test_value_' + randomId;
                await db.execute(
                    'INSERT INTO settings (key, value) VALUES ($1, $2)',
                    ['test_key_' + randomId, randomValue]
                );
                
                // 测试查询数据
                const result = await db.select('SELECT * FROM settings');
                console.log('查询结果:', result);
                
            } catch (error: any) {
                setTestResult('错误: ' + error);
                console.error('数据库测试失败:', error);
            }
        };

        testDB();
    }, []);

    return (
        <div className="p-4">
            <h2 className="text-lg font-bold mb-4">数据库测试</h2>
            <div className="bg-gray-100 p-4 rounded">
                <pre>{testResult}</pre>
            </div>
        </div>
    );
}