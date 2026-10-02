using System;

namespace SampleNamespace
{
    public class SampleCalculator
    {
        private int _total = 0;

        public int Add(int x)
        {
            _total += x;
            return _total;
        }

        public int GetTotal()
        {
            return _total;
        }
    }
}
