# Notes

`Router/` 提供笔记及文件夹接口；`Domain/Dto/` 是 HTTP 对象，`Domain/Po/` 是修改台账表映射；`Service/NoteChanges.py` 是正式笔记写入的唯一协调入口。`Mapper/` 保存台账读写；`Storage/Markdown/` 读写正文，`Storage/Version/` 保存影子 Git 版本。草稿审批和恢复必须调用正式写入流程。
