namespace Dashboard.Services;

/// <summary>One tunable parameter of a strategy, for the descriptions on the simulate page.</summary>
public sealed record ParamInfo(string Name, string Default, string Meaning, string Range);

/// <summary>Display text for one strategy: what it does and what can be tuned. Defaults match the Engine (3 / 4 players).</summary>
public sealed record StrategyDoc(string Id, string Title, string Summary, string[] Rules, ParamInfo[] Params);

public static class StrategyInfo
{
    private const string Threshold = "建造階段時，一棟建築的「價值」要達到這個數字才會買（也影響要不要選 Builder）。太低會買一堆沒用的建築，太高會幾乎不買，對每個流派都很敏感。";

    public static readonly IReadOnlyList<StrategyDoc> All = new StrategyDoc[]
    {
        new("corn-shipper", "玉米出貨流",
            "多種玉米、每次出貨都出玉米拿勝利點；只買少數有用的建築。",
            new[]
            {
                "優先拿玉米種植園（玉米不需要生產建築，出貨就有分）。",
                "只買少數有用的建築：Hacienda（通常第 1 回合）、倉庫、Hospice、Construction Hut，之後視金幣買 Harbor、Wharf；價值低於 buildThreshold 的不買。",
                "選 Captain 時盡量出玉米；先派殖民者給玉米種植園。",
                "其餘行為使用共用的基本打分規則（見 HeuristicStrategy）。",
            },
            new[] { new ParamInfo("buildThreshold", "4 人 4.0／3 人 5.0", Threshold, "3～4.5 幾乎相同；5.5 以上勝率大幅下降") }),

        new("corn-to-premium", "玉米轉菸草／咖啡流",
            "前期打玉米，中期改種菸草或咖啡，蓋對應的生產建築後賣給交易所換金幣。",
            new[]
            {
                "前期行為與玉米出貨流相同。",
                "進入中期的條件：回合數達到 switchRound，或玉米種植園達到 cornTarget 塊（先到的算）。",
                "中期在菸草與咖啡中挑「比較容易拿到」的那一種（已有的生產建築、已有的種植園、翻開的種植園），蓋對應生產建築、派殖民者、貨物賣給交易所。",
                "仍會出貨玉米；Trader 角色的價值乘上 traderWeight。",
            },
            new[]
            {
                new ParamInfo("switchRound", "4 人 7／3 人 9", "到第幾回合就進入中期（轉向菸草／咖啡）。", "5～9，影響不大"),
                new ParamInfo("cornTarget", "4 人 4／3 人 5", "玉米種植園拿到幾塊就進入中期。", "3～5"),
                new ParamInfo("traderWeight", "1.5", "中期選 Trader 角色的價值倍率。", "1～1.5 較好；0.5 或 2 以上較差"),
                new ParamInfo("buildThreshold", "4 人 4.0／3 人 5.0", Threshold, "3～4 較好；6 以上較差"),
            }),

        new("harbor-rush", "港口流",
            "先想辦法蓋出港口（每次出貨多 1 分），之後靠多次、多種貨物的出貨得分。",
            new[]
            {
                "蓋到港口之前，除了港口什麼都不買；賣貨、收角色金幣、拿採石場／建造特權折扣來湊錢，湊夠錢第一時間選 Builder。",
                "蓋到港口後想要「很多次分開的出貨」：玉米／靛藍／糖多種貨物、Wharf、盡量多選 Captain。",
                "拿種植園時兩個選項分數完全相同，固定順序：Hacienda > 玉米 > 糖 > 靛藍 > 菸草 > 咖啡 > 採石場（糖先於靛藍較好；可用文字參數 tieTile 覆寫，空字串＝關閉）。",
                "4 人局：先累積 harborReadyTiles 塊種植園（或到 harborReadyRound 回合）才開始搶港口，之前先走一般經濟；3 人局一開始就搶（等待在 3 人局反而變差）。",
            },
            new[]
            {
                new ParamInfo("quarryTarget", "0", "蓋港口前要拿幾個採石場（採石場讓建築變便宜）。", "0～1，更多沒有幫助"),
                new ParamInfo("harborReadyTiles", "4 人 7／3 人 0", "4 人局：擁有幾塊種植園／採石場後才開始搶港口；0 = 一開始就搶。", "6～8 較好；9 以上較差"),
                new ParamInfo("harborReadyRound", "4 人 8／3 人 0", "到第幾回合無論如何開始搶港口。", "6～8"),
                new ParamInfo("buildThreshold", "4.0", Threshold, "3～4.5；6 以上較差"),
            }),

        new("build-first", "建築優先流",
            "把金幣盡快變成建築，目標是能拿滿終局加分的大型建築。",
            new[]
            {
                "拿採石場（建築折扣），種混合作物（靛藍、糖、菸草、咖啡），賣貨換金幣。",
                "只要有值得買又買得起的建築就選 Builder。",
                "大型建築依「加分拿不拿得滿」來挑：Residence（種植園多）、City Hall（紫色建築多）、Guild Hall（生產建築多）、Fortress（殖民者多）、Customs House（勝利點籌碼多）。",
                "派殖民者時先派給建築，再派給種植園。",
                "拿種植園時兩個選項分數完全相同，固定順序：Hacienda > 玉米 > 糖 > 靛藍 > 菸草 > 咖啡 > 採石場（糖先於靛藍較好；可用文字參數 tieTile 覆寫，空字串＝關閉）。",
            },
            new[]
            {
                new ParamInfo("buildThreshold", "4 人 4.5／3 人 3.5", Threshold, "4 人局 4.5 最好（3.5 以下差很多）；3 人局 3.5"),
                new ParamInfo("quarryTarget", "3", "最多拿幾個採石場。", "2～3；4 以上較差"),
            }),

        new("cheap-engine", "便宜引擎流",
            "由 MCTS 的打法整理而來：很早買便宜的 1 分建築，只種很少的種植園，頻繁小量出貨。",
            new[]
            {
                "早期買便宜的 1 分建築：小靛藍工廠、小糖廠、小市場，加上 Hospice；之後買大靛藍工廠、大糖廠。",
                "種植園只拿玉米／靛藍／糖，而且很少：擁有 tileCap 塊後就不再選 Settler。",
                "不買 Hacienda；採石場價值低。",
                "手上有貨就選 Captain 出貨（次數多、每次量少）；有小市場時 Trader 價值較高。",
            },
            new[]
            {
                new ParamInfo("buildThreshold", "2.0", Threshold, "1～2 最好；3 以上較差"),
                new ParamInfo("tileCap", "4", "擁有幾塊種植園後，不再選 Settler 職業（其他玩家選 Settler 時仍會拿到種植園）。", "3～4 最好；8 以上差很多"),
                new ParamInfo("smallValue", "8", "便宜的 1 分建築（小靛藍、小糖廠、小市場）的價值。", "8 以上都一樣；6 以下較差"),
                new ParamInfo("roleCoinWeight", "1", "選職業時，職業卡上每枚金幣（以及 Prospector 的 1 枚）值多少分。", "4 人局 2、3 人局 2.5 明顯較好（第 13 輪掃描，分析文件第 9 節）；4 以上變差"),
            }),

        new("wharf-rush", "Wharf 私船流",
            "先農一陣子，湊到錢（採石場折價）買 Wharf，之後每次船長階段把最大的一堆貨全數丟上私船。",
            new[]
            {
                "前期（種植園不到 wharfReadyTiles 塊且未到 wharfReadyRound 回合）：玉米為主，加靛藍／糖，用預設經濟，不急著買 Wharf。",
                "起跑後：除了 Wharf 什麼都不買；拿 quarryTarget 個採石場（每個折 1 元，最多折 3 元），賣靛藍／糖等換金幣，一湊到 9 元就選 Builder。",
                "Wharf 買到後：優先派殖民者給 Wharf，再買倉庫（讓大堆貨撐過船長階段）與 Harbor（每次出貨 +1 分）；不一定要買 Harbor。",
                "出貨：私船永遠先裝最大的一堆（無視容量與公家船，整堆都算分），其餘貨再裝公家船；倉庫保留數量最多的那堆；手上有大堆貨時多選 Captain。",
                "玉米不賣（那是私船要出的主力）。",
                "拿種植園時兩個選項分數完全相同，固定順序：Hacienda > 玉米 > 糖 > 靛藍 > 菸草 > 咖啡 > 採石場（玉米必須先於採石場；糖先於靛藍較好；可用文字參數 tieTile 覆寫，空字串＝關閉）。",
            },
            new[]
            {
                new ParamInfo("quarryTarget", "3", "起跑後最多拿幾個採石場（Wharf 折價上限 3 元）。", "3 以上都一樣；0 差很多"),
                new ParamInfo("wharfReadyTiles", "7", "種植園／採石場拿到幾塊就開始買 Wharf。", "7 以上差不多；3～5 較差"),
                new ParamInfo("wharfReadyRound", "4 人 6／3 人 4", "到第幾回合就開始買 Wharf（與上一項先到的算）。", "4 人局 6～8；3 人局 4～6"),
                new ParamInfo("smallPlant", "4 人 5.5／3 人 8", "買 Wharf 之前，小靛藍工廠／小糖廠的價值（賣貨湊錢的來源）。", "3 人局 8 較好（+1.5 個百分點）；4 人局無差"),
                new ParamInfo("traderWeight", "4 人 1／3 人 3", "存錢買 Wharf 時，Trader 角色價值的倍率。", "3 人局 2～3；4 人局 1"),
                new ParamInfo("moneyTile", "5", "靛藍／糖種植園的價值（起跑後 +1）。", "5 最好；9 會崩"),
                new ParamInfo("cornTile", "9", "玉米種植園的價值。", "9 以上一樣"),
                new ParamInfo("earlyQuarry", "6", "起跑前採石場的價值。", "6；提早搶採石場（9 以上）沒有幫助"),
                new ParamInfo("buildThreshold", "4.0", Threshold, "預設即可"),
            }),

        new("wharf-premium", "Wharf 私船流（菸草／咖啡籌錢）",
            "Wharf 流的變體：先建立菸草或咖啡的生產，賣給交易所籌 9 元買 Wharf，之後照樣把最大一堆貨丟上私船。",
            new[]
            {
                "第一階段：在菸草與咖啡中挑比較容易拿到的一種，拿它的種植園（也拿玉米），先買對應的生產建築（Tobacco Storage／Coffee Roaster）。",
                "第二階段（有生產建築、還沒 Wharf）：除了 Wharf 什麼都不買；菸草／咖啡一律賣掉換金幣，Trader 價值乘上 traderWeight；最多拿 quarryTarget 個採石場。",
                "第三階段（有 Wharf）：私船先裝最大的一堆，其餘裝公家船；買倉庫與 Harbor；sellAfterWharf=1 時售價 3 元以上的貨仍會賣。",
                "買 Wharf 之前，選 Captain 只看玉米能出多少（菸草／咖啡留著賣錢）。",
            },
            new[]
            {
                new ParamInfo("traderWeight", "2.5", "還沒買到 Wharf 時 Trader 角色價值的倍率。", "1～2.5 幾乎相同"),
                new ParamInfo("quarryTarget", "1", "最多拿幾個採石場。", "0～3 幾乎相同"),
                new ParamInfo("sellAfterWharf", "1", "買到 Wharf 後是否仍賣高價貨（1 = 賣，0 = 全留著出貨）。", "1 略好（+0.5 個百分點）"),
                new ParamInfo("cornTile", "7", "玉米種植園的價值（目標貨種的種植園是 9.5）。", "7～9；5 較差"),
                new ParamInfo("buildThreshold", "4.0", Threshold, "預設即可"),
            }),

        new("corn-monopoly", "玉米壟斷派（搗亂）",
            "只想參加的搗亂者：霸占所有玉米種植園，玉米囤著不賣也不出貨，把有限的玉米供應區吃光。",
            new[]
            {
                "種植園只拿玉米（連翻開的玉米也搶），選 Settler 的價值在有玉米可拿時最高。",
                "玉米貨物不賣、不主動出貨；Captain 角色價值為 0，被迫出貨時先出別的貨，最後才出玉米。",
                "只買倉庫（把玉米囤過船長階段）、Hacienda、Hospice；其他建築一概不買。",
                "派殖民者給玉米種植園與倉庫；選 Craftsman 時看重玉米產量（供應區只有 10 個玉米，囤光了別人就沒有）。",
            },
            new[] { new ParamInfo("buildThreshold", "4.0", Threshold, "預設即可") }),

        new("corn-monopoly-tiles", "玉米壟斷派：只搶種植園",
            "壟斷派的變體，用來拆開兩種搗亂手段：只霸占玉米種植園，貨物照常出貨與販賣。",
            new[]
            {
                "種植園只拿玉米（翻開的玉米也搶），有玉米可拿時搶著選 Settler。",
                "其餘行為與玉米出貨流相同：照常出貨、照常買建築。",
            },
            new[] { new ParamInfo("buildThreshold", "4.0", Threshold, "預設即可") }),

        new("corn-monopoly-hoard", "玉米壟斷派：只囤貨",
            "壟斷派的變體，用來拆開兩種搗亂手段：種植園照玉米出貨流的方式拿，但玉米囤著不賣、不出貨。",
            new[]
            {
                "種植園的選擇與玉米出貨流相同（沒有特別搶）。",
                "玉米不賣、不主動出貨；Captain 價值為 0，被迫出貨時先出別的貨；只買倉庫、Hacienda、Hospice。",
            },
            new[] { new ParamInfo("buildThreshold", "4.0", Threshold, "預設即可") }),

        new("mcts", "MCTS 樹搜尋",
            "每個決策都用大量隨機模擬找出最好的動作；最強但很慢，適合只跑數百局。",
            new[]
            {
                "每個決策：複製目前狀態、重洗看不到的種植園牌堆，做 simulations 次模擬。",
                "每次模擬：沿搜尋樹（UCT）往下選 → 展開一個沒試過的動作 → 由 rolloutStrategy 控制所有座位往下打 rolloutRounds 回合 → 以當時的分數排名回傳。",
                "最後選被訪問最多次的動作。可看到完整狀態（包含對手的勝利點籌碼），但沒有偷看牌堆。",
                "只用模擬次數限制運算量（不用時間），所以同一份設定與種子可以完全重現。",
            },
            new[]
            {
                new ParamInfo("simulations", "200", "每個決策的模擬次數；越多越強也越慢（大致成正比）。", "100 次約能打平手寫策略，300 次大幅勝出"),
                new ParamInfo("exploration", "0.7", "UCT 的探索係數（獎勵在 0～1 之間）。", "0.5～1.0"),
                new ParamInfo("rolloutRounds", "8", "模擬時往下打幾回合就停止並以當時分數排名；0 = 打到終局。", "5～8；3 太短；8 與打到終局一樣強但快一倍"),
                new ParamInfo("rolloutStrategy", "random（文字參數，填 rolloutStrategy=random）", "模擬時所有座位使用的策略名稱，不能是 mcts。隨機最準，手寫策略與 guided-random 反而較差。", "random"),
                new ParamInfo("rolloutMaxDecisions", "3000", "單次模擬最多決策數（安全上限）。", "一般不用改"),
                new ParamInfo("valueModel", "空白（文字參數，填 valueModel=ml/models/4p-v1.txt）", "學習得到的局面價值函數（LightGBM 文字模型 .txt 或 MLP .json，見 ml/README.md）。設定後葉節點不再 rollout 到第 rolloutRounds 回合，改由模型估計每個座位的回傳值；rolloutRounds 被忽略。", "依人數用對應的模型"),
                new ParamInfo("leafRollout", "0", "有 valueModel 時，展開後先由 rolloutStrategy 打幾個決策再估值；0 = 直接估值。", "0 或 20"),
            }),

        new("random", "亂選動作",
            "每次從合法動作中均勻隨機挑一個，當作最弱的基準。",
            new[] { "沒有任何策略；用來確認其他策略真的比亂打強。" },
            Array.Empty<ParamInfo>()),

        new("guided-random", "加權隨機",
            "隨機，但依動作種類加權：很少 Pass，偏好出貨、建造、賣貨、拿種植園。",
            new[] { "實驗中當 MCTS 的模擬策略反而比純隨機差（有偏好的模擬評估較不準）。" },
            Array.Empty<ParamInfo>()),
    };

    /// <summary>Tabs of the strategy descriptions: strategies grouped by their main good / plan.</summary>
    public sealed record StrategyGroup(string Key, string Title, string Hint, string[] Ids);

    public static readonly IReadOnlyList<StrategyGroup> Groups = new StrategyGroup[]
    {
        new("corn", "🌽 玉米", "主貨是玉米：出貨、轉高價貨，或霸占玉米搗亂。",
            new[] { "corn-shipper", "corn-to-premium", "corn-monopoly", "corn-monopoly-tiles", "corn-monopoly-hoard" }),
        new("ship", "⚓ 港口／私船", "靠 Harbor 或 Wharf 的出貨加成拿分。",
            new[] { "harbor-rush", "wharf-rush", "wharf-premium" }),
        new("build", "🏗️ 建築", "把金幣變成建築：大型建築的終局加分，或便宜的 1 分建築。",
            new[] { "build-first", "cheap-engine" }),
        new("search", "🎲 搜尋／隨機", "不是手寫規則：樹搜尋與當基準的隨機玩家。",
            new[] { "mcts", "random", "guided-random" }),
    };

    /// <summary>Strategies of a group in group order; a key that is not a group (e.g. "all") returns every strategy.</summary>
    public static IEnumerable<StrategyDoc> InGroup(string key)
    {
        var g = Groups.FirstOrDefault(x => x.Key == key);
        return g == null ? All : g.Ids.Select(id => All.First(d => d.Id == id));
    }
}
