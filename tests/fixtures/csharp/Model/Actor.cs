namespace Game.Model
{
    public abstract class Actor
    {
        protected internal int health;

        public abstract void Act();

        public virtual bool IsAlive() { return health > 0; }
    }

    public interface IScorable
    {
        int Score { get; }
        int ComputeScore(System.Collections.Generic.Dictionary<string, int> bonuses);
    }

    public enum Faction
    {
        Neutral = 0,
        Ally = 1,
        Enemy = 2,
    }

    public class Item
    {
        public string Id;
    }
}
