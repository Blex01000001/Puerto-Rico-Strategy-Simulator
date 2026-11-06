namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 1 (tile pile), section 4 (Settler, Hacienda, Hospice)

    /// <summary>Draws one random plantation from the pile, reshuffling the discard pile first if the pile is empty. Returns -1 if none.</summary>
    private static int DrawPlantation(GameState s)
    {
        int total = s.DeckTotal();
        if (total == 0)
        {
            if (s.DiscardTotal() == 0) return -1;
            for (int g = 0; g < G; g++) { s.Deck[g] += s.Discard[g]; s.Discard[g] = 0; }
            total = s.DeckTotal();
        }

        int pick = Rng.NextInt(ref s.RngState, total);
        for (int g = 0; g < G; g++)
        {
            if (pick < s.Deck[g])
            {
                s.Deck[g]--;
                return g;
            }
            pick -= s.Deck[g];
        }
        throw new InvalidOperationException("unreachable");
    }

    /// <summary>Turns up plantations until players + 1 are showing (or no tiles remain).</summary>
    internal static void FlipFaceUp(GameState s)
    {
        int showing = 0;
        for (int g = 0; g < G; g++) showing += s.FaceUp[g];
        while (showing < GameConstants.FaceUpTiles(s.PlayerCount))
        {
            int g = DrawPlantation(s);
            if (g < 0) break;
            s.FaceUp[g]++;
            showing++;
        }
    }

    /// <summary>End of the Settler phase: unclaimed face-up tiles go to the discard pile, then new ones are turned up.</summary>
    private static void DiscardAndFlip(GameState s)
    {
        for (int g = 0; g < G; g++) { s.Discard[g] += s.FaceUp[g]; s.FaceUp[g] = 0; }
        FlipFaceUp(s);
    }

    /// <summary>Hospice: a newly gained tile receives a colonist from the bank (else the ship).</summary>
    private static void HospiceFor(GameState s, int seat, int tileType)
    {
        if (!s.HasOccupied(seat, BuildingId.Hospice)) return;
        if (TakeSpareColonist(s)) s.TilesOcc[seat * T + tileType]++;
    }

    private static void GainTile(GameState s, int seat, int tileType)
    {
        s.Tiles[seat * T + tileType]++;
        HospiceFor(s, seat, tileType);
    }

    private static void FillSettler(GameState s, List<GameAction> a)
    {
        int p = s.Actor;
        if (s.TileCount(p) >= GameConstants.MaxTiles) return; // island full: nothing to do

        a.Add(GameAction.Pass);
        if (s.HaciendaUsed == 0 && s.HasOccupied(p, BuildingId.Hacienda) && s.DeckTotal() + s.DiscardTotal() > 0)
            a.Add(new GameAction(ActionType.UseHacienda));
        for (int g = 0; g < G; g++)
            if (s.FaceUp[g] > 0) a.Add(new GameAction(ActionType.TakePlantation, g));
        if (s.QuarrySupply > 0 && (p == s.CurrentOwner || s.HasOccupied(p, BuildingId.ConstructionHut)))
            a.Add(new GameAction(ActionType.TakeQuarry));
    }

    private static void ApplySettler(GameState s, GameAction a)
    {
        int p = s.Actor;
        switch (a.Type)
        {
            case ActionType.Pass:
                NextActor(s);
                break;
            case ActionType.UseHacienda:
                s.HaciendaUsed = 1;
                GainTile(s, p, DrawPlantation(s));
                break; // same actor decides again (Fill handles a full island)
            case ActionType.TakePlantation:
                s.FaceUp[a.A]--;
                GainTile(s, p, a.A);
                NextActor(s);
                break;
            case ActionType.TakeQuarry:
                s.QuarrySupply--;
                GainTile(s, p, GameConstants.QuarryType);
                NextActor(s);
                break;
            default:
                throw new InvalidOperationException($"{a} is not a Settler action");
        }
    }
}
