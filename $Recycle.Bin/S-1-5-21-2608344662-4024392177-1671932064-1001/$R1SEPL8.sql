USE [myCompany]
GO

/****** Object:  Table [dbo].[StateCountry]    Script Date: 2/26/2024 3:36:28 PM ******/
SET ANSI_NULLS ON
GO


IF OBJECT_ID(N'dbo.StateCountry',N'U') IS NOT NULL
DROP TABLE [dbo].[StateCountry]
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[StateCountry](
	[StateCountryId] [int] IDENTITY(1,1) NOT NULL,
	[StateId] [int] NULL,
	[CountryId] [int] NULL,
 CONSTRAINT [PK_StateCountry] PRIMARY KEY CLUSTERED 
(
	[StateCountryId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[StateCountry]  WITH CHECK ADD  CONSTRAINT [FK_StateCountry_Country] FOREIGN KEY([CountryId])
REFERENCES [dbo].[Country] ([ContryId])
GO

ALTER TABLE [dbo].[StateCountry] CHECK CONSTRAINT [FK_StateCountry_Country]
GO

ALTER TABLE [dbo].[StateCountry]  WITH CHECK ADD  CONSTRAINT [FK_StateCountry_State] FOREIGN KEY([StateId])
REFERENCES [dbo].[State] ([StateId])
GO

ALTER TABLE [dbo].[StateCountry] CHECK CONSTRAINT [FK_StateCountry_State]
GO

