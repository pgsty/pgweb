# Index AM 百科

`/wiki/indexam/` 收录六种内置索引访问方法：B-tree、Hash、GiST、SP-GiST、GIN、BRIN。能力矩阵、方法详情和版本变化页面复用中文 Wiki 外壳、版本条与分类筛选。表访问方法、FDW 和扩展索引方法不混入此清单。

路由保持稳定：索引 `/wiki/indexam/`；详情 `/wiki/indexam/<slug>/?v=<major>&from=<major>`；变化 `/wiki/indexam/changes/<major>/?from=<major>`。未知版本返回 404，大写方法名带筛选参数跳转到小写身份。切换版本保留索引筛选和比较起点；变化页的表单不提交未声明的 `v` 参数。

八种能力分别记录有序输出、唯一键、多列键、INCLUDE、仅索引扫描、距离排序、并行扫描与并行构建。技术状态保持 `yes/no/conditional/unknown`，界面分别显示“支持／不支持／有条件／未确定”。未知到支持意味着证据可用性变化，不证明该版本首次引入能力。

原始来源及哈希保留英文来源坐标，中文译文与核验哈希放在 `localization.sources`；能力声明不是运行时实测。版本比较只比较能力状态与存储参数名称清单，明确排除来源构建变化，不声称覆盖所有算法、性能或参数定义变化。手册中没记录的方法与未知能力分别展示。

数据沿用共享固定快照导入流程；完整性和来源校验由 `index_method_data.validate()` 与共享导入器负责，运行时不生成来源内容。

```sh
.venv/bin/python manage.py test pgweb.wiki.test_specialized_readers --noinput
```
