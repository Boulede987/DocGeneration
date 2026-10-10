using System;
using System.Collections.Generic;
using Game.Model;
using Game.Model.Enemies;

namespace Game.Core
{
    public sealed class GameManager : IDisposable
    {
        private Player player;
        private readonly Pool<Enemy> enemies = new Pool<Enemy>();
        public Logger Log;

        public void Tick(Item item)
        {
            Stats stats = player.ComputeScore(null) > 0 ? new Stats() : default;
            Logger.Log("tick");
        }

        public void Dispose() { }
    }

    public class Pool<T> where T : Actor, new()
    {
        private readonly Queue<T> free = new Queue<T>();

        public T Rent() { return free.Count > 0 ? free.Dequeue() : new T(); }
    }

    public static class Logger
    {
        public static void Log(string message) { }
    }
}
