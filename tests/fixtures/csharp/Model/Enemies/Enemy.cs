namespace Game.Model.Enemies;

public class Enemy : Actor
{
    private Item loot;
    private Faction faction;
    public Item[] Drops { get; set; }

    public override void Act()
    {
        Item dropped = new Item();
    }
}

public class Logger
{
    public static void Log(string message) { }
}
