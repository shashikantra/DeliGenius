using System;
using System.Collections.Generic;

namespace Demo_Project.Models;

public partial class Manager
{
    public int ManagerId { get; set; }

    public string ManagerFirstName { get; set; } = null!;

    public string ManagerLastName { get; set; } = null!;

    public virtual ICollection<Employee> Employees { get; set; } = new List<Employee>();
}
