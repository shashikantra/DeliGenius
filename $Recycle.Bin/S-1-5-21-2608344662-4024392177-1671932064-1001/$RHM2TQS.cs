using System;
using System.Collections.Generic;

namespace Demo_Project.Models;

public partial class Manager
{
    public int ManagerId { get; set; }

    public string ManagerFirstName { get; set; } = null!;

    public string ManagerLastName { get; set; } = null!;
}
