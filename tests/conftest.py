"""测试环境的最小化环境准备。

app.py 在导入阶段执行 _enforce_exposure_policy()：面板口令为默认 admin/admin
且 HOST 为非环回地址时直接拒绝启动。开发机上的 .env 常同时满足这两个条件，
导入 app 会抛出 SystemExit，导致整套测试在收集阶段中断。

conftest.py 早于任何测试模块导入，在此把 HOST 固定为环回地址即可。
load_dotenv 默认不覆盖已存在的环境变量，因此这里设置的值优先于 .env；
CI 环境本就没有 .env，该默认值与未设置时的行为一致，不改变被测语义。
"""

import os

os.environ.setdefault("HOST", "127.0.0.1")
# 开发机 .env 可能显式放行默认口令。该键在 app.py 导入时由 load_dotenv 读回，
# 而 load_dotenv 默认不覆盖已存在的环境变量，因此这里先以空值占位：键存在即被
# 跳过，安全用例得以继续验证「默认拒绝」这一被测语义。
os.environ.setdefault("DEEPSEEKER_ALLOW_DEFAULT_ADMIN", "")
