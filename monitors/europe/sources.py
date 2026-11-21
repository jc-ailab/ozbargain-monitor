"""Public destination windows and narrowly scoped claims to recheck."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Stop:
    key: str
    country: str
    name: str
    windows: tuple[tuple[str, str], ...]
    note: str = ''

    def dates(self):
        for first, last in self.windows:
            yield date.fromisoformat(first), date.fromisoformat(last)


STOPS = (
    Stop('athens', '希腊', '雅典', (('2026-11-25', '2026-11-27'),)),
    Stop('tarragona', '西班牙', '塔拉戈纳', (('2026-12-04', '2026-12-06'), ('2026-12-19', '2026-12-19'))),
    Stop('barcelona', '西班牙', '巴塞罗那', (('2026-12-05', '2026-12-05'), ('2026-12-19', '2026-12-21')),
         '12/5 为可选停留，12/21 为转城日'),
    Stop('malaga', '西班牙', '马拉加', (('2026-12-08', '2026-12-08'),)),
    Stop('cadiz', '西班牙', '加的斯', (('2026-12-11', '2026-12-11'),)),
    Stop('valencia', '西班牙', '瓦伦西亚', (('2026-12-16', '2026-12-16'),)),
    Stop('palma', '西班牙', '帕尔马', (('2026-12-17', '2026-12-17'),)),
    Stop('madrid', '西班牙', '马德里', (('2026-12-21', '2026-12-24'),), '12/24 为离城日'),
)


@dataclass(frozen=True)
class Offer:
    title: str
    category: str
    price: str
    reason: str
    evidence: str
    access: str = '到场'
    # Restrict recurring offers or dated events to eligible local visit dates.
    weekdays: tuple[int, ...] = tuple(range(7))
    first: str = '2026-11-25'
    last: str = '2026-12-24'
    priority: int = 0
    pricing: str = 'fixed'


@dataclass(frozen=True)
class Source:
    key: str
    stop: str
    name: str
    url: str
    offers: tuple[Offer, ...]
    requirements: tuple[tuple[str, str], ...] = ()


def outlet(key, city, name, slug, brand, category, reason):
    return Source(key, city, name, f'https://www.thebicestercollection.com/{slug}', (
        Offer(brand, category, '', reason, 'Village price', '实体奥莱店', priority=2, first='2026-12-19', pricing='outlet'),
    ))


SOURCES = (
    Source('neon', 'athens', 'NEON 艺术基金会', 'https://neon.org.gr/en/exhibition/i-think-ill-go-now/', (
        Offer('I Think I’ll Go Now', '活动与演出', '免费', '雅典本地编舞家的现场作品，11/26 晚 21:00 演出，先预约。',
              r'26\s*[–-]\s*29 November 2026\s*\|\s*9:00 pm\s*FREE ENTRANCE\s*Reservation required',
              '官方预约到场', first='2026-11-26', last='2026-11-26', priority=3),
    )),
    Source('emst', 'athens', '希腊国家当代艺术博物馆', 'https://www.emst.gr/en/visit', (
        Offer('EMST 当代艺术博物馆 · 年龄优惠', '景点与门票', '€5（全价 €10）',
              '65 岁以上的游客可按馆方减价规则参观，带年龄证明到票台。',
              r'General admission\s+10\s*€\s+5\s*€.{0,400}visitors over 65', '现场票台', (1, 2, 3, 4, 5, 6)),
        Offer('EMST 当代艺术博物馆 · 二次入馆', '景点与门票', '一张票可入馆两次',
              '买票后 30 天内能再入馆一次，适合把展览分两天慢慢看。',
              r'2 FOR 1.{0,150}a second time within 30 days', '现场票台', (1, 2, 3, 4, 5, 6)),
    )),
    Source('pharmacy295', 'athens', 'Pharmacy295 · APIVITA', 'https://www.pharmacy295.gr/f/apivita-2', (
        Offer('APIVITA 蜂胶洁面泡沫 300ml', '护肤与美妆', '',
              '希腊本土品牌的洁面大瓶装，访客可网上下单到雅典周边药房免费自提，收到可取通知后再出发。',
              r'Άμεσα Διαθέσιμο APIVITA\s*-\s*PROMO PACK CLEANSING FOAM[^€]{0,190}300ml',
              '游客下单 · 门店自提', last='2026-11-26', priority=2, pricing='pharmacy'),
    ), (
        ('https://www.pharmacy295.gr/f/click-n-collect', r'δωρεάν Click & Collect στα 5 φαρμακεία μας στην Αττική'),
        ('https://www.pharmacy295.gr/f/tropoi-paraggelias', r'ως επισκέπτης χωρίς να δημιουργήσετε λογαριασμό'),
    )),
    Source('tarragona', 'tarragona', '塔拉戈纳旅游局', 'https://www.tarragonaturisme.cat/es/monumento/pretorio-y-circo-romano-mht', (
        Offer('罗马马戏场与执政官塔', '景点与门票', '€5',
              '一张低价门票可看古罗马马戏场遗迹和执政官塔，周日提前闭馆。',
              r'Horarios y precios\s+Precio\s+5\s*€.{0,700}1 noviembre\s*-\s*23 diciembre 2026',
              '现场票台或官方订票', (1, 2, 3, 4, 5, 6)),
    )),
    Source('picasso-bcn', 'barcelona', '巴塞罗那毕加索博物馆', 'https://museupicassobcn.cat/planifica-la-visita/horaris-i-preus', (
        Offer('巴塞罗那毕加索博物馆', '景点与门票', '网上 €14／现场 €15',
              '提前在官网买票比现场少 €1，一张票含常设与临时展。',
              r'Col·lecció\s*\+\s*exposicions temporals\s*En línia:\s*14\s*€\s*Taquilles:\s*15\s*€',
              '官方电子票', (1, 2, 3, 4, 5, 6)),
    )),
    outlet('roca-bimba', 'barcelona', 'La Roca Village · BIMBA Y LOLA',
           'la-roca-village/en/brands/bimba-y-lola/', 'BIMBA Y LOLA · 巴塞罗那奥莱', '服装与时尚',
           '西班牙品牌的包袋和服饰可现场挑选，奥莱标价与店内库存请到店核对。'),
    Source('roca-munich', 'barcelona', 'La Roca Village · MUNICH',
           'https://www.thebicestercollection.com/la-roca-village/en/brands/munich/', (
        Offer('MUNICH · 巴塞罗那奥莱', '鞋履', '部分款标示最高减 60%',
              '加泰罗尼亚运动鞋品牌可现场试穿，折扣、尺码和库存请到店核对。',
              r'MUNICH Outlet Barcelona\s*\|\s*Up to 60% Off', '实体奥莱店', first='2026-12-19', priority=2),
    )),
    Source('picasso-malaga', 'malaga', '马拉加毕加索博物馆', 'https://www.museopicassomalaga.org/en/visita', (
        Offer('马拉加毕加索博物馆 · 年龄优惠', '景点与门票', '€11（全价 €13）',
              '65 岁以上的游客可用优惠票看毕加索馆，12/8 假日营业时间请在订票页确认。',
              r'€13\s*/\s*€11 reduced.{0,2500}Seniors over age 65', '现场票台或官方订票'),
    )),
    Source('tavira', 'cadiz', 'Torre Tavira 官方', 'https://torretavira.com/en/horarios-tarifas-y-localizacion', (
        Offer('Torre Tavira 暗箱观景塔 · 年龄优惠', '景点与门票', '长者优惠',
              '65 岁以上可用长者票看暗箱实时投影与老城全景，先看官方预约时段。',
              r'Over 65s', '现场票台或官方预约'),
    )),
    Source('carme', 'valencia', '瓦伦西亚博物馆联盟', 'https://www.consorcimuseus.gva.es/museos/centre-del-carme-cultura-contemporania/?lang=es', (
        Offer('Centre del Carme 当代文化中心', '景点与门票', '免费',
              '老城原修道院改成当代艺术展馆，可免费进场，周三开放。',
              r'martes a domingo, de 10:00 a 20:00 horas.{0,1100}Entrada gratuita', '现场入场', (1, 2, 3, 4, 5, 6)),
    )),
    Source('esbaluard', 'palma', 'Es Baluard 当代艺术博物馆', 'https://esbaluard.org/en/visit/', (
        Offer('Es Baluard 当代艺术博物馆 · 骑车票', '景点与门票', '€2（全价 €8）',
              '骑车到馆可用 €2 票，比全价省 €6，适合本来就想骑行逛帕尔马的人。',
              r'General ticket\s+8,00\s*€.{0,480}Come by bike\s+2,00\s*€', '现场票台', (1, 2, 3, 4, 5, 6)),
    )),
    Source('prado', 'madrid', '马德里官方旅游局', 'https://www.esmadrid.com/en/tourist-information/museo-del-prado', (
        Offer('普拉多博物馆 · 晚间免费', '景点与门票', '免费',
              '可在晚间免费时段看哥雅和委拉斯开兹，先确认当天开放时段和预约要求。',
              r'Free admission.{0,400}6.{0,40}8\s*pm', '官方免费票', (0, 1, 2), priority=3),
    )),
    Source('can-bonet', 'madrid', 'Can Bonet 官方', 'https://www.canbonetmadrid.com/descubre-el-exquisito-menu-mediodia-de-can-bonet-en-madrid/', (
        Offer('Can Bonet 加泰罗尼亚午市套餐', '餐馆', '€20.90／人',
              '丽池公园附近可到店吃三道菜加饮品的午餐，周一至周四 13:00–16:00，节假日除外。',
              r'de lunes a jueves de 13:00\s*h a 16:00\s*h\s*\(excepto festivos\).{0,120}20,90\s*€',
              '餐厅堂食', (0, 1, 2)),
    )),
    outlet('rozas-bimba', 'madrid', 'Las Rozas Village · BIMBA Y LOLA',
           'las-rozas-village/en/brands/bimba-y-lola/', 'BIMBA Y LOLA · 马德里奥莱', '服装与时尚',
           '西班牙品牌的包袋和服饰可现场挑选，奥莱标价与店内库存请到店核对。'),
)

# Public sources checked during admission. Do not retry blocked sites automatically.
UNAVAILABLE = (
    ('Chollometro', 'https://www.chollometro.com/ofertas', 'robots.txt 返回 403，未准入'),
    ('Skroutz', 'https://www.skroutz.gr/', 'robots.txt 返回 403，未准入'),
    ('BestPrice', 'https://www.bestprice.gr/', 'robots.txt 未能在超时前读取，未准入'),
    ('Benaki Museum', 'https://www.benaki.org/', 'robots.txt 返回 403，未准入'),
    ('attica 美妆', 'https://www.atticadps.gr/prosfores/omorfias/', 'robots.txt 返回 403，未准入'),
    ('Hondos Center', 'https://www.hondoscenter.com/el/prosfores.html', '优惠页返回 403，未准入'),
    ('APIVITA', 'https://www.apivita.com/', 'robots.txt 返回 403，未准入'),
)
