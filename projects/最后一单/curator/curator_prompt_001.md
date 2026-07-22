# Curator状态更新任务 — 第1章

你是一个剧本状态管理员。根据第1章的正文，生成状态变更提案。

## 第1章正文

```
# 第一章：最后一单

手机震了。

陈默看了一眼屏幕——万达广场B座2301，酸菜鱼，备注：不要葱。

他把手机塞回口袋，发动电动车。轮胎碾过积水，溅起一片浑浊的水花。凌晨一点的街道空荡荡的，只有路灯在雾气里发出昏黄的光。

2301。他默念了一遍这个数字。不是他刻意记的，是它自己钻进脑子里的。三年前开始，每一个订单号、每一条地址、每一张客户的脸，都像被人用刀刻在骨头上一样，想忘都忘不掉。

万达广场B座，电梯到23楼，左转第三家。门铃坏了，敲三下。酸菜鱼不要葱，筷子两双，醋包一个。

他停在B座楼下，摘下头盔。楼道灯是声控的，他跺了一下脚，灯亮了，照出墙上的小广告和地上的烟头。

电梯到了23楼。他走到2301门口，抬手敲门。

三下。

没人应。

他又敲了三下。

还是没人。

陈默低头看了一眼外卖袋上的订单时间——凌晨12点47分下单，现在1点12分。超时了。

他掏出手机，拨客户的电话。

"嘟——嘟——嘟——"

没人接。

他靠在墙上等。楼道里的灯灭了，他又跺了一下脚。灯亮的时候，他注意到门缝下面有一道暗红色的痕迹。

陈默蹲下来。

那道痕迹从门缝里渗出来，沿着地砖的缝隙蔓延了半米。他用手指碰了一下——粘的，温的。

血。

他的手指缩了回来。

手机又震了。是一条短信："外卖放门口就行。"

陈默盯着那条短信。发件人的号码是刚才下单的号码，但短信的语气不对——太冷静了，像是早就准备好的模板。

他站起来，把外卖放在门口。

然后他掏出手机，对着那道血迹拍了一张照片。

不是他想拍的。是他的手自己动的。三年前那场车祸，他也是这样——明明想跑，脚却钉在地上，眼睛死死盯着那辆翻倒的车。

他转身走向电梯。

电梯门关上的瞬间，他听到2301的门开了。

他没有回头看。

出了楼，陈默跨上电动车，发动。轮胎碾过刚才的积水，水花溅到他的裤腿上。他没有擦。

手机又震了。

是妹妹发来的微信："哥，今天的药钱凑够了吗？"

陈默盯着那条消息，打了三个字："快够了。"

他把手机塞回口袋，抬头看了一眼23楼的窗户。

灯亮着。

窗帘后面，有一个人影站在那里，正往下看。

```

## 当前角色状态

- char_pro (陈默, protagonist): location=出租屋, health=疲惫，有黑眼圈, goal=攒钱给妹妹治病
- char_ant (王建国, antagonist): location=高档小区, health=健康, goal=除掉任何可能揭露真相的人
- char_ally (林小雨, supporting): location=报社宿舍, health=健康, goal=找到连环案的突破口

## 未解决的伏笔

- thread_1: 三年前的车祸和现在的连环案有关联 (status=open)
- thread_2: 林小雨父亲的死另有隐情 (status=open)
- thread_3: 陈默妹妹的医药费快凑够了，但真相可能会让他失去一切 (status=open)

## 信息对称性矩阵

- info_1: 陈默三年前目睹的车祸 (known_by=['char_pro'])
- info_2: 王建国是连环杀手 (known_by=['char_ant'])
- info_3: 林小雨父亲的死和王建国有关 (known_by=['char_ant'])

## 你的任务

生成一个JSON对象，包含以下变更提案：

```json
{
  "changes": [
    {
      "entity_type": "character",
      "entity_id": "char_xxx",
      "field_path": "state.location",
      "old_value": "旧值",
      "new_value": "新值",
      "chapter": 1,
      "machine_verifiable": true,
      "reason": "变更原因"
    }
  ],
  "new_events": [
    {
      "id": "evt_xxx",
      "chapter": 1,
      "timestamp": "故事内时间",
      "description": "事件描述",
      "characters_involved": ["char_xxx"],
      "location": "地点",
      "impact": "影响",
      "type": "事件类型"
    }
  ],
  "new_plot_threads": [
    {
      "id": "thread_xxx",
      "description": "新伏笔描述",
      "planted_chapter": 1,
      "importance": "major/minor"
    }
  ],
  "plot_thread_updates": [
    {
      "id": "thread_xxx",
      "status": "payoff",
      "payoff_chapter": 1,
      "resolution": "如何收束"
    }
  ],
  "info_asymmetry_updates": [
    {
      "info_id": "info_xxx",
      "description": "新信息描述",
      "known_by": ["char_xxx"],
      "chapter_revealed": 1,
      "is_protagonist_advantage": true/false
    }
  ]
}
```

## 规则

1. 只报告本章实际发生的变更，不要推测未来
2. machine_verifiable=true 的变更才写入硬约束（位置、生死、数值变化）
3. 角色的情感变化、态度变化标记为 machine_verifiable=false（软状态）
4. 伏笔状态：open→planted（埋下）→payoff（收束）→abandoned（放弃）
5. 信息差更新：谁在本章知道了什么新信息

只输出JSON，不要输出其他文字。
