import type { NuclearSite } from '@/types/contracts';

/**
 * 核设施静态种子（后端 `nuclear_sites.json` 未就绪时的兜底数据源）。
 *
 * 生效规则（与 `lib/nuclearData.mergeNuclear` 一致）：
 * - feed 的 `sites[]` **非空** ⇒ 完全覆盖本种子（后端为准）；
 * - feed 缺文件 / `sites` 缺字段 / `sites` 为空数组 ⇒ 回落本种子（K5 一级降级：不白屏）。
 *
 * ⚠ **坐标性质声明**：以下为**公开百科级近似坐标**，统一小数 4 位（≈11m，K4），
 * 精度足够上图但**不作权威**。站点清单是否为这 6 站、坐标是否需校正，
 * 属设计稿 §10-N7 待确认项，后端 feed 就绪后一律以 feed 为准。
 *
 * 本文件只放**站点静态属性**，不放任何读数：读数属于 `readings[]`，
 * 只能来自后端；前端不编造辐射数值（避免把占位数字误读成真实监测值）。
 */
export const NUCLEAR_SEED: NuclearSite[] = [
  {
    id: 'zaporizhzhia',
    name: '扎波罗热核电站',
    name_en: 'Zaporizhzhia NPP',
    country: '乌克兰',
    lat: 47.5122,
    lng: 34.5853,
    type: 'npp',
    note: '欧洲最大核电站，位于战区',
  },
  {
    id: 'chernobyl',
    name: '切尔诺贝利核电站',
    name_en: 'Chornobyl NPP',
    country: '乌克兰',
    lat: 51.3892,
    lng: 30.0994,
    type: 'legacy',
    note: '1986 事故遗址，禁区监测',
  },
  {
    id: 'fukushima-daiichi',
    name: '福岛第一核电站',
    name_en: 'Fukushima Daiichi NPP',
    country: '日本',
    lat: 37.4211,
    lng: 141.0328,
    type: 'legacy',
    note: '2011 事故 / 处理水排放议题',
  },
  {
    id: 'bushehr',
    name: '布什尔核电站',
    name_en: 'Bushehr NPP',
    country: '伊朗',
    lat: 28.8296,
    lng: 50.8856,
    type: 'npp',
    note: '中东核议题焦点',
  },
  {
    id: 'yongbyon',
    name: '宁边核设施',
    name_en: 'Yongbyon Nuclear Scientific Research Center',
    country: '朝鲜',
    lat: 39.7975,
    lng: 125.755,
    type: 'npp',
    note: '半岛核议题焦点',
  },
  {
    id: 'three-mile-island',
    name: '三里岛核电站',
    name_en: 'Three Mile Island NPP',
    country: '美国',
    lat: 40.1531,
    lng: -76.7247,
    type: 'legacy',
    note: '1979 事故 / 重启议题',
  },
];

/** 站点类型 → 中文标签（面板与 tooltip 共用，避免各处自己写 map）。 */
export const NUCLEAR_TYPE_LABEL: Record<NonNullable<NuclearSite['type']>, string> = {
  npp: '核电站',
  monitor: '监测站',
  legacy: '事故遗址',
};
